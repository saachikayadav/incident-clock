"""IncidentClock web service - pod common interface, Phase 3 increment.

Request flow:  HTTP -> observability/auth middleware (request id, timing, 401)
               -> route handler (404 existence check -> 400 body validation)
               -> Store (PostgreSQL, single transaction) -> JSON response.

Check order (Phase 2 Model 4, as implemented): 401 -> 405 (method) -> 404 -> 400 -> 409.
Operations scheduled for Phases 4-5 are routed and authenticated, return 404 for an
unknown incident, and otherwise return 501 NOT_IMPLEMENTED.
"""

from __future__ import annotations

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
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import logs
from .config import load_settings
from .db import Store
from .errors import ApiError, error_response, not_found, not_implemented
from .validation import parse_json_object, to_utc, validate_evidence, validate_incident

PUBLIC_PATHS = {"/health", "/openapi.yaml"}
CONTRACT_PATH = Path(__file__).resolve().parent.parent / "openapi" / "contract.yaml"


def create_app() -> FastAPI:
    logs.setup()
    settings = load_settings()
    store = Store(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await run_in_threadpool(store.open)
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
        return error_response(exc.status, exc.code, exc.message)

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
                response: Response = error_response(401, "UNAUTHORIZED", "missing or invalid X-API-Key header")
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
            response = error_response(500, "INTERNAL_ERROR", "unexpected server error")
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


def _key_ok(request: Request, expected: str) -> bool:
    supplied = request.headers.get("x-api-key", "")
    return bool(supplied) and hmac.compare_digest(supplied.encode(), expected.encode())


app = create_app()
