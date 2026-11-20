"""IncidentClock web service - pod common interface, Phase 5 increment.

Request flow:  HTTP -> observability/auth middleware (request id, timing, 401)
               -> route handler (404 existence check -> 400 body validation)
               -> deadline module (app/deadline.py) where a date is needed
               -> Store (PostgreSQL, one transaction: lock incident, 409 state check, INSERT)
               -> JSON response.

Check order (Phase 2 Model 4, as implemented): 401 -> 405 (method) -> 404 -> 400 -> 409.
Phase 4 added decisions (REQ-04/05/08/09), deadline status (REQ-10) and filings (REQ-11).
Phase 5 adds corrections (REQ-06: a new decision supersedes the current one, which stays in
the history) and the timeline with evidence summary (REQ-12). Every contract operation is
now implemented.

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

from . import coverage_session, deadline, logs
from .config import load_settings
from .db import StateConflict, Store, UnknownDecision, UnknownEvidence, status_of
from .docs_page import DOCS_HTML
from .errors import ApiError, error_response, invalid, not_found
from .validation import (
    parse_as_of,
    parse_json_object,
    to_utc,
    validate_correction,
    validate_decision,
    validate_evidence,
    validate_filing,
    validate_incident,
)

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
        current = inc["current_decision"]
        filing = inc["filing"]
        body: dict[str, Any] = {
            "incidentId": inc["incident_id"],
            "title": inc["title"],
            "description": inc["description"],
            "discoveredAt": to_utc(inc["discovered_at"]),
            "reporterName": inc["reporter_name"],
            "status": status_of(current["decision"] if current else None, filing is not None),
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
            "currentDecision": None if current is None else decision_body(current),
            "filing": None if filing is None else filing_body(filing),
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

    # ---- Phase 4: decisions, deadline status, filing ----------------------

    @app.post("/incidents/{incidentId}/decisions")
    async def record_decision(incidentId: str, request: Request) -> JSONResponse:
        seq = await require_incident(incidentId)  # 404 before 400
        data = parse_json_object(await request.body())
        state = await run_in_threadpool(store.incident_state, seq)
        dec = validate_decision(data, discovered_at=state["discovered_at"], now=datetime.now(UTC))
        due = None
        if dec.decision == "MATERIAL":
            try:
                due = deadline.filing_deadline(dec.determined_at)
            except deadline.OutsideCalendar as exc:
                raise invalid("determinedAt", str(exc)) from None
        try:
            row = await run_in_threadpool(store.record_decision, seq, dec, due)
        except UnknownEvidence as exc:
            raise invalid(
                "evidenceIds", "must reference evidence of this incident; not found: " + ", ".join(exc.evidence_ids)
            ) from None
        except StateConflict as exc:
            raise ApiError(409, "STATE_CONFLICT", exc.message) from None
        logs.log(
            "info",
            "decision_recorded",
            incident_id=incidentId,
            decision_id=row["decision_id"],
            decision=dec.decision,
            determined_date_et=deadline.eastern_date(dec.determined_at).isoformat(),
            deadline=None if due is None else due.isoformat(),
        )
        return JSONResponse(
            status_code=201,
            content={
                "decisionId": row["decision_id"],
                "status": row["status"],
                "deadline": None if due is None else due.isoformat(),
            },
        )

    @app.get("/incidents/{incidentId}/deadline-status")
    async def get_deadline_status(incidentId: str, as_of: str | None = None) -> JSONResponse:
        seq = await require_incident(incidentId)
        moment = parse_as_of(as_of) or datetime.now(UTC)
        state = await run_in_threadpool(store.incident_state, seq)
        due = None
        if state["status"] == "MATERIAL_PENDING_FILING":
            due = state["current_decision"]["deadline"]
        status, days = deadline.deadline_status(due, moment)
        return JSONResponse(
            status_code=200,
            content={"status": status, "deadline": None if due is None else due.isoformat(), "businessDays": days},
        )

    @app.post("/incidents/{incidentId}/filing")
    async def record_filing(incidentId: str, request: Request) -> JSONResponse:
        seq = await require_incident(incidentId)
        data = parse_json_object(await request.body())
        fil = validate_filing(data, now=datetime.now(UTC))
        filed_day = deadline.eastern_date(fil.filed_at)

        def timeliness(due: Any) -> tuple[str, int]:
            late = deadline.days_late(due, filed_day)
            return ("LATE" if late else "ON_TIME"), late

        try:
            row = await run_in_threadpool(store.record_filing, seq, fil, timeliness)
        except StateConflict as exc:
            raise ApiError(409, "STATE_CONFLICT", exc.message) from None
        return JSONResponse(
            status_code=201,
            content={
                "filingId": row["filing_id"],
                "status": "FILED",
                "timeliness": row["timeliness"],
                "businessDaysLate": row["business_days_late"],
            },
        )

    # ---- Phase 5: corrections, timeline ------------------------------------

    @app.post("/incidents/{incidentId}/corrections")
    async def record_correction(incidentId: str, request: Request) -> JSONResponse:
        seq = await require_incident(incidentId)  # 404 before 400
        data = parse_json_object(await request.body())
        state = await run_in_threadpool(store.incident_state, seq)
        cor = validate_correction(data, discovered_at=state["discovered_at"], now=datetime.now(UTC))
        dec = cor.decision
        due = None
        if dec.decision == "MATERIAL":
            # REQ-06: the deadline follows the correcting decision's own determination date.
            try:
                due = deadline.filing_deadline(dec.determined_at)
            except deadline.OutsideCalendar as exc:
                raise invalid("determinedAt", str(exc)) from None
        try:
            row = await run_in_threadpool(store.record_correction, seq, cor, due)
        except UnknownEvidence as exc:
            raise invalid(
                "evidenceIds", "must reference evidence of this incident; not found: " + ", ".join(exc.evidence_ids)
            ) from None
        except UnknownDecision as exc:
            raise invalid(
                "correctsDecisionId", f"must reference a decision of this incident; not found: {exc.decision_id}"
            ) from None
        except StateConflict as exc:
            raise ApiError(409, "STATE_CONFLICT", exc.message) from None
        logs.log(
            "info",
            "decision_corrected",
            incident_id=incidentId,
            decision_id=row["decision_id"],
            corrects=cor.corrects_decision_id,
            decision=dec.decision,
            determined_date_et=deadline.eastern_date(dec.determined_at).isoformat(),
            deadline=None if due is None else due.isoformat(),
        )
        return JSONResponse(
            status_code=201,
            content={
                "decisionId": row["decision_id"],
                "status": row["status"],
                "deadline": None if due is None else due.isoformat(),
            },
        )

    @app.get("/incidents/{incidentId}/timeline")
    async def timeline(incidentId: str) -> JSONResponse:
        seq = await require_incident(incidentId)
        t = await run_in_threadpool(store.timeline, seq)
        counts = t["evidence_counts"]
        days = None
        if t["determined_at"] is not None:
            # Calendar days between the Eastern Time dates, the same day convention as the
            # REQ-09 deadline (docs/spec-issues.md ISSUE-25).
            days = (deadline.eastern_date(t["determined_at"]) - deadline.eastern_date(t["discovered_at"])).days
        return JSONResponse(
            status_code=200,
            content={
                "incidentId": incidentId,
                "events": [
                    {
                        "eventType": e["event_type"],
                        "recordedAt": to_utc(e["recorded_at"]),
                        "referenceId": e["reference_id"],
                    }
                    for e in t["events"]
                ],
                "evidenceCounts": {
                    "technical": counts.get("TECHNICAL", 0),
                    "businessImpact": counts.get("BUSINESS_IMPACT", 0),
                    "legal": counts.get("LEGAL", 0),
                    "other": counts.get("OTHER", 0),
                },
                "discoveryToDeterminationDays": days,
            },
        )

    return app


def decision_body(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "decisionId": d["decision_id"],
        "decision": d["decision"],
        "determinedAt": to_utc(d["determined_at"]),
        "decidedBy": d["decided_by"],
        "rationale": d["rationale"],
        "evidenceIds": d["evidence_ids"],
        "deadline": None if d["deadline"] is None else d["deadline"].isoformat(),
    }


def filing_body(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "filingId": f["filing_id"],
        "filedAt": to_utc(f["filed_at"]),
        "accessionNumber": f["accession_number"],
        "timeliness": f["timeliness"],
        "businessDaysLate": f["business_days_late"],
    }


def _source_for(request: Request) -> str | None:
    """/test/* error bodies must name a source; project API errors keep the pod format."""
    return "system" if request.url.path.startswith("/test/") else None


def _key_ok(request: Request, expected: str) -> bool:
    supplied = request.headers.get("x-api-key", "")
    return bool(supplied) and hmac.compare_digest(supplied.encode(), expected.encode())


app = create_app()
