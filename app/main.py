"""IncidentClock web service - pod common interface, Phase 3 increment.

Request flow:  HTTP -> observability/auth middleware (request id, timing, 401)
               -> route handler (404 existence check -> 400 body validation)
               -> Store (PostgreSQL, single transaction) -> JSON response.

Check order (Phase 2 Model 4, as implemented): 401 -> 405 (method) -> 404 -> 400 -> 409.
Operations scheduled for Phases 4-5 are routed and authenticated, return 404 for an
unknown incident, and otherwise return 501 NOT_IMPLEMENTED.

Course cross-team testing interface (system side): POST /test/setup prepares a session
(clears project data, starts per-session code coverage) and GET /test/report returns
that coverage. Error bodies on /test/* carry {"message", "source"} as that interface
requires. One session is active at a time; a new setup supersedes the previous one.
"""

from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import coverage_session, logs
from .config import load_settings
from .db import Store
from .docs_page import DOCS_HTML
from .errors import ApiError, error_response, not_found, not_implemented
from .validation import parse_json_object, to_utc, validate_evidence, validate_incident

PUBLIC_PATHS = {"/health", "/openapi.yaml", "/openapi/system-test-interface.yaml", "/docs"}
MAX_SESSION_ID_LEN = 200
OPENAPI_DIR = Path(__file__).resolve().parent.parent / "openapi"
CONTRACT_PATH = OPENAPI_DIR / "contract.yaml"
TEST_INTERFACE_PATH = OPENAPI_DIR / "system-test-interface.yaml"


def create_app() -> FastAPI:
    logs.setup()
    settings = load_settings()
    store = Store(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await run_in_threadpool(store.open)
        coverage_session.finish_baseline()
        logs.log("info", "startup", version=settings.version)
        yield
        store.close()
        logs.log("info", "shutdown", version=settings.version)

    app = FastAPI(
        title="IncidentClock",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,  # the contract is served verbatim at /openapi.yaml instead
    )

    # ---- error handling --------------------------------------------------

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        request.state.error_code = exc.code
        return error_response(exc.status, exc.code, exc.message, exc.source)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 405:
            code, msg = (
                "METHOD_NOT_ALLOWED",
                f"{request.method} is not allowed on {request.url.path}; records are append-only",
            )
        elif exc.status_code == 404:
            code, msg = "NOT_FOUND", f"no operation at {request.url.path}"
        else:
            code, msg = "HTTP_ERROR", str(exc.detail)
        request.state.error_code = code
        resp = error_response(exc.status_code, code, msg)
        if exc.headers:
            resp.headers.update(exc.headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request.state.error_code = "INVALID_REQUEST"
        return error_response(400, "INVALID_REQUEST", "request is malformed")

    # ---- middleware: request id, auth, timing, structured logging --------

    @app.middleware("http")
    async def _observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        request.state.error_code = None
        try:
            if request.url.path not in PUBLIC_PATHS and not _key_ok(request, settings.api_key):
                request.state.error_code = "UNAUTHORIZED"
                response: Response = error_response(
                    401, "UNAUTHORIZED", "missing or invalid X-API-Key header", _source_for(request)
                )
            else:
                response = await call_next(request)
        except Exception as exc:  # unexpected server error: log it, never leak details
            logs.log(
                "error",
                "unhandled_exception",
                request_id=request_id,
                path=request.url.path,
                exception=type(exc).__name__,
                detail=str(exc)[:300],
            )
            request.state.error_code = "INTERNAL_ERROR"
            response = error_response(500, "INTERNAL_ERROR", "unexpected server error", _source_for(request))
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Service-Version"] = settings.version
        logs.log(
            "warning" if response.status_code >= 400 else "info",
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
            error_code=request.state.error_code,
            version=settings.version,
        )
        return response

    # ---- helpers ---------------------------------------------------------

    async def require_incident(incident_id: str) -> int:
        seq = await run_in_threadpool(store.find_incident_seq, incident_id)
        if seq is None:
            raise not_found("incident", incident_id)
        return seq

    # ---- operations ------------------------------------------------------

    @app.get("/health")
    async def health() -> JSONResponse:
        ok = await run_in_threadpool(store.ping)
        if not ok:
            return JSONResponse(status_code=503, content={"status": "DATABASE_UNAVAILABLE"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.get("/openapi.yaml")
    async def contract() -> PlainTextResponse:
        text = CONTRACT_PATH.read_text()
        return PlainTextResponse(text, media_type="application/yaml")

    @app.get("/openapi/system-test-interface.yaml")
    async def test_interface_spec() -> PlainTextResponse:
        return PlainTextResponse(TEST_INTERFACE_PATH.read_text(), media_type="application/yaml")

    @app.get("/docs")
    async def docs() -> HTMLResponse:
        """Interactive API docs (Swagger UI); requests from the page still need the API key."""
        return HTMLResponse(DOCS_HTML)

    @app.post("/reset")
    async def reset() -> JSONResponse:
        await run_in_threadpool(store.reset)
        logs.log("warning", "reset", detail="all test data cleared")
        return JSONResponse(status_code=200, content={"status": "RESET_COMPLETE"})

    @app.post("/incidents")
    async def create_incident(request: Request) -> JSONResponse:
        data = parse_json_object(await request.body())
        inc = validate_incident(data, now=datetime.now(UTC))
        row = await run_in_threadpool(store.create_incident, inc)
        return JSONResponse(status_code=201, content={"incidentId": row["incident_id"], "status": "OPEN"})

    @app.get("/incidents/{incidentId}")
    async def get_incident(incidentId: str) -> JSONResponse:
        found = await run_in_threadpool(store.get_incident, incidentId)
        if found is None:
            raise not_found("incident", incidentId)
        inc, evidence = found
        body: dict[str, Any] = {
            "incidentId": inc["incident_id"],
            "title": inc["title"],
            "description": inc["description"],
            "discoveredAt": to_utc(inc["discovered_at"]),
            "reporterName": inc["reporter_name"],
            "status": derive_status(),
            "evidence": [
                {
                    "evidenceId": e["evidence_id"],
                    "category": e["category"],
                    "summary": e["summary"],
                    "source": e["source"],
                    "collectedAt": to_utc(e["collected_at"]),
                    "recordedAt": to_utc(e["recorded_at"]),
                }
                for e in evidence
            ],
            "currentDecision": None,  # decisions arrive in Phase 4 (REQ-04)
            "filing": None,  # filings arrive in Phase 5 (REQ-11)
        }
        return JSONResponse(status_code=200, content=body)

    @app.post("/incidents/{incidentId}/evidence")
    async def add_evidence(incidentId: str, request: Request) -> JSONResponse:
        seq = await require_incident(incidentId)  # 404 before 400 (check order)
        data = parse_json_object(await request.body())
        ev = validate_evidence(data, now=datetime.now(UTC))
        row = await run_in_threadpool(store.add_evidence, seq, ev)
        return JSONResponse(
            status_code=201,
            content={"evidenceId": row["evidence_id"], "recordedAt": to_utc(row["recorded_at"])},
        )

    # ---- course cross-team testing interface (system side) ---------------

    setup_lock = asyncio.Lock()
    # Process start: coverage for a session set up before a restart was lost with the process.
    process_started = datetime.now(UTC)

    @app.post("/test/setup")
    async def test_setup(request: Request) -> JSONResponse:
        data = parse_json_object(await request.body(), source="system")
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ApiError(400, "INVALID_SESSION_ID", "session_id must be a non-empty string", "system")
        if len(session_id) > MAX_SESSION_ID_LEN:
            raise ApiError(
                400, "INVALID_SESSION_ID", f"session_id must be at most {MAX_SESSION_ID_LEN} characters", "system"
            )
        if "setup" in data and data["setup"] is not None and not isinstance(data["setup"], dict):
            raise ApiError(400, "INVALID_SETUP", "setup must be a JSON object", "system")
        async with setup_lock:
            previous = await run_in_threadpool(store.active_test_session)
            if previous is not None and previous == session_id:
                raise ApiError(409, "SESSION_EXISTS", f"session {session_id} already exists", "system")
            frozen = coverage_session.freeze() if previous is not None else None
            try:
                created = await run_in_threadpool(store.prepare_test_session, session_id, frozen)
            except Exception as exc:
                logs.log("error", "test_setup_failed", session_id=session_id, exception=type(exc).__name__)
                raise ApiError(500, "SETUP_FAILED", "could not initialize the session database", "system") from exc
            if not created:
                raise ApiError(409, "SESSION_EXISTS", f"session {session_id} already exists", "system")
            coverage_session.start_session()
        logs.log("warning", "test_setup", session_id=session_id, superseded=previous)
        return JSONResponse(status_code=201, content={"session_id": session_id})

    @app.get("/test/report")
    async def test_report(session_id: str | None = None) -> JSONResponse:
        if not session_id or not session_id.strip():
            raise ApiError(400, "INVALID_SESSION_ID", "session_id query parameter is required", "system")
        row = await run_in_threadpool(store.get_test_session, session_id)
        if row is None:
            raise ApiError(404, "UNKNOWN_SESSION", f"session {session_id} does not exist", "system")
        active = await run_in_threadpool(store.active_test_session)
        if row["frozen_coverage"] is not None:
            code = row["frozen_coverage"]
        elif session_id == active and row["created_at"] >= process_started:
            code = coverage_session.snapshot()
        else:
            code = {
                "covered": None,
                "total": None,
                "basis": "Source lines; measurement lost because the service restarted after this session's setup",
            }
        return JSONResponse(status_code=200, content={"session_id": session_id, "coverage": {"code": code}})

    # ---- Phase 4/5 operations: routed, authenticated, 404-aware, not yet implemented

    @app.post("/incidents/{incidentId}/decisions")
    async def record_decision(incidentId: str) -> JSONResponse:
        await require_incident(incidentId)
        raise not_implemented("POST /incidents/{incidentId}/decisions")

    @app.post("/incidents/{incidentId}/corrections")
    async def record_correction(incidentId: str) -> JSONResponse:
        await require_incident(incidentId)
        raise not_implemented("POST /incidents/{incidentId}/corrections")

    @app.get("/incidents/{incidentId}/deadline-status")
    async def deadline_status(incidentId: str) -> JSONResponse:
        await require_incident(incidentId)
        raise not_implemented("GET /incidents/{incidentId}/deadline-status")

    @app.post("/incidents/{incidentId}/filing")
    async def record_filing(incidentId: str) -> JSONResponse:
        await require_incident(incidentId)
        raise not_implemented("POST /incidents/{incidentId}/filing")

    @app.get("/incidents/{incidentId}/timeline")
    async def timeline(incidentId: str) -> JSONResponse:
        await require_incident(incidentId)
        raise not_implemented("GET /incidents/{incidentId}/timeline")

    return app


def derive_status() -> str:
    """Status is derived, never stored (Phase 2, Q3.3).

    With no decision or filing records yet (Phases 4-5), every incident is OPEN.
    """
    return "OPEN"


def _source_for(request: Request) -> str | None:
    """/test/* error bodies must name a source; project API errors keep the pod format."""
    return "system" if request.url.path.startswith("/test/") else None


def _key_ok(request: Request, expected: str) -> bool:
    supplied = request.headers.get("x-api-key", "")
    return bool(supplied) and hmac.compare_digest(supplied.encode(), expected.encode())


app = create_app()
