"""IncidentClock tester service - course cross-team testing interface (tester side).

POST /test/setup  {"target_url"}   -> creates a session, prepares the target via its
                                      POST /test/setup, returns 201 {"session_id"}
POST /test/run    {"session_id"}   -> runs the contract suite (tests/, non-provisional)
                                      against the target once, returns the suite report
GET  /test/report ?session_id=...  -> stored report; 409 until the suite has ended

The test plan is the same pytest suite used in CI, run in a subprocess with
BASE_URL/API_KEY pointing at the target, so the oracles are identical everywhere.

Security: the target's API key is sent only to targets registered in the TARGETS
environment variable (JSON object {"https://base-url": "api-key", ...}). Any other
target_url is rejected with 400, so the tester cannot be used to leak keys.
Sessions and reports live in memory: a restart or free-plan spin-down clears them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import reporting

ROOT = Path(__file__).resolve().parent.parent
SETUP_TIMEOUT = float(os.environ.get("TESTER_SETUP_TIMEOUT_SECONDS", "120"))
RUN_TIMEOUT = float(os.environ.get("TESTER_RUN_TIMEOUT_SECONDS", "600"))
REQUEST_TIMEOUT = float(os.environ.get("TESTER_REQUEST_TIMEOUT_SECONDS", "60"))
VERSION = (os.environ.get("SERVICE_VERSION") or os.environ.get("RENDER_GIT_COMMIT") or "dev")[:12]


class TesterError(Exception):
    __test__ = False  # not a pytest test class

    def __init__(self, status: int, message: str, source: str) -> None:
        super().__init__(message)
        self.status, self.message, self.source = status, message, source


def _err(status: int, message: str, source: str = "tester") -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message, "source": source})


def load_targets() -> dict[str, str]:
    raw = os.environ.get("TARGETS", "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise RuntimeError('TARGETS must be a JSON object {"https://base-url": "api-key"}')
    return {normalize(k): v for k, v in data.items()}


def normalize(url: str) -> str:
    return url.strip().rstrip("/")


def validate_target_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TesterError(400, "target_url must be a non-empty string", "tester")
    url = normalize(value)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise TesterError(400, "target_url must be an absolute http(s) URL", "tester")
    if parts.query or parts.fragment or "@" in parts.netloc:
        raise TesterError(400, "target_url must not contain a query, fragment, or credentials", "tester")
    if parts.path.endswith("/test"):
        raise TesterError(400, "target_url is the system base URL, without the /test suffix", "tester")
    return url


class Session:
    def __init__(self, session_id: str, target_url: str) -> None:
        self.session_id = session_id
        self.target_url = target_url
        self.state = "ready"  # ready -> running -> done | aborted
        self.report: dict[str, Any] | None = None
        self.created_at = datetime.now(UTC)


def create_app() -> FastAPI:
    targets = load_targets()
    sessions: dict[str, Session] = {}
    lock = threading.Lock()
    app = FastAPI(title="IncidentClock tester", docs_url=None, redoc_url=None, openapi_url=None)

    def log(event: str, **fields: Any) -> None:
        print(
            json.dumps(
                {
                    "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                    "event": event,
                    "version": VERSION,
                    **fields,
                }
            ),
            flush=True,
        )

    @app.exception_handler(TesterError)
    async def _tester_error(_: Request, exc: TesterError) -> JSONResponse:
        return _err(exc.status, exc.message, exc.source)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _err(exc.status_code, f"{request.method} {request.url.path}: {exc.detail}")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log("unhandled_exception", exception=type(exc).__name__, detail=str(exc)[:300])
        return _err(500, f"tester failure: {type(exc).__name__}")

    async def json_body(request: Request) -> dict[str, Any]:
        try:
            data = json.loads(await request.body() or b"null")
        except ValueError:
            raise TesterError(400, "request body is not valid JSON", "tester") from None
        if not isinstance(data, dict):
            raise TesterError(400, "request body must be a JSON object", "tester")
        return data

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "targets": sorted(targets)}

    # ---- POST /test/setup --------------------------------------------------

    @app.post("/test/setup")
    async def setup(request: Request) -> JSONResponse:
        data = await json_body(request)
        target = validate_target_url(data.get("target_url"))
        if target not in targets:
            raise TesterError(
                400,
                f"target_url is not a registered pod target; registered: {', '.join(sorted(targets)) or 'none'}",
                "tester",
            )
        session_id = str(uuid.uuid4())
        status, body = await run_in_threadpool(_prepare_target, target, targets[target], session_id)
        if status != 201:
            log("setup_failed", session_id=session_id, target=target, status=status, source=body.get("source"))
            return _err(status, body["message"], body["source"])
        with lock:
            sessions[session_id] = Session(session_id, target)
        log("setup", session_id=session_id, target=target)
        return JSONResponse(status_code=201, content={"session_id": session_id})

    # ---- POST /test/run ----------------------------------------------------

    @app.post("/test/run")
    async def run(request: Request) -> JSONResponse:
        data = await json_body(request)
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise TesterError(400, "session_id must be a non-empty string", "tester")
        with lock:
            session = sessions.get(session_id)
            if session is None:
                raise TesterError(404, f"unknown session {session_id}", "tester")
            if session.state != "ready":
                raise TesterError(
                    409,
                    f"session {session_id} has already run ({session.state}); create a new session to repeat the suite",
                    "tester",
                )
            session.state = "running"
        log("run_start", session_id=session_id, target=session.target_url)
        report, abort_message = await run_in_threadpool(_run_suite, session, targets[session.target_url])
        with lock:
            session.report = report
            session.state = "aborted" if abort_message else "done"
        log("run_end", session_id=session_id, state=session.state, summary=report.get("summary"))
        if abort_message:
            return _err(500, f"tester aborted: {abort_message}; stored report available at /test/report")
        return JSONResponse(status_code=200, content=report)

    # ---- GET /test/report --------------------------------------------------

    @app.get("/test/report")
    async def report(session_id: str | None = None) -> JSONResponse:
        if not session_id or not session_id.strip():
            raise TesterError(400, "session_id query parameter is required", "tester")
        with lock:
            session = sessions.get(session_id)
            if session is None:
                raise TesterError(404, f"unknown session {session_id}", "tester")
            if session.report is None:
                raise TesterError(409, f"suite for session {session_id} has not ended ({session.state})", "tester")
            return JSONResponse(status_code=200, content=session.report)

    return app


def _prepare_target(target: str, key: str, session_id: str) -> tuple[int, dict[str, str]]:
    """Call the target's POST /test/setup and translate the outcome for our caller."""
    try:
        r = httpx.post(
            f"{target}/test/setup",
            json={"session_id": session_id, "setup": {}},
            headers={"X-API-Key": key},
            timeout=SETUP_TIMEOUT,
        )
    except httpx.TimeoutException:
        return 500, {"message": f"target setup did not respond within {SETUP_TIMEOUT:.0f} s", "source": "communication"}
    except httpx.TransportError as exc:
        return 500, {"message": f"could not reach target setup: {type(exc).__name__}", "source": "communication"}
    try:
        body = r.json()
    except ValueError:
        body = None
    if r.status_code == 201:
        if isinstance(body, dict) and body.get("session_id") == session_id:
            return 201, {}
        return 500, {"message": "target setup returned 201 without the same session_id", "source": "system"}
    message = body.get("message") if isinstance(body, dict) else None
    source = body.get("source") if isinstance(body, dict) else None
    return r.status_code, {
        "message": message
        if isinstance(message, str) and message.strip()
        else f"target setup returned HTTP {r.status_code}",
        "source": source if source in ("tester", "system", "communication", "unknown") else "system",
    }


def _run_suite(session: Session, key: str) -> tuple[dict[str, Any], str | None]:
    started = time.monotonic()
    started_at = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="tester-") as tmp:
        out = Path(tmp)
        env = {
            **os.environ,
            "BASE_URL": session.target_url,
            "API_KEY": key,
            "TESTER_OUT_DIR": str(out),
            "TESTER_TRACE_FILE": str(out / "trace.jsonl"),
            "TEST_TIMEOUT_SECONDS": str(REQUEST_TIMEOUT),
            "PYTHONPATH": str(ROOT),
        }
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-p",
            "tester.plugin",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "-m",
            "not provisional",
            "-q",
            "--no-header",
            "-rN",
        ]
        abort: str | None = None
        try:
            proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=RUN_TIMEOUT)  # noqa: S603
            if proc.returncode not in (0, 1):  # 0 all passed, 1 some failed; anything else = abort
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or ["no output"]
                abort = f"test runner exited with code {proc.returncode} ({tail[0][:200]})"
        except subprocess.TimeoutExpired:
            abort = f"suite exceeded the {RUN_TIMEOUT:.0f} s run limit"
        except Exception as exc:  # the tester itself failed
            abort = f"{type(exc).__name__}: {exc}"

        planned = json.loads((out / "planned.json").read_text()) if (out / "planned.json").exists() else []
        recorded = (
            [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
            if (out / "results.jsonl").exists()
            else []
        )
        if not planned and abort is None:
            abort = "no tests were collected"
        results = reporting.assemble_results(planned, recorded, abort is not None, abort or "")
        component = reporting.component_coverage(out / "trace.jsonl")

    system_report, problem = _fetch_system_report(session, key)
    report = {
        "session_id": session.session_id,
        "target_url": session.target_url,
        "results": results,
        "coverage": {
            "code": reporting.code_coverage(system_report, problem),
            "component": component,
            "system": reporting.system_coverage(results),
        },
        "summary": reporting.summarize(results),
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.monotonic() - started, 1),
        "tester_version": VERSION,
    }
    return report, abort


def _fetch_system_report(session: Session, key: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        r = httpx.get(
            f"{session.target_url}/test/report",
            params={"session_id": session.session_id},
            headers={"X-API-Key": key},
            timeout=REQUEST_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        return None, f"request to /test/report failed ({type(exc).__name__})"
    if r.status_code != 200:
        return None, f"/test/report returned HTTP {r.status_code}"
    try:
        body = r.json()
    except ValueError:
        return None, "/test/report body is not JSON"
    return (body, None) if isinstance(body, dict) else (None, "/test/report body is not a JSON object")


app = create_app()
