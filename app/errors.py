"""Contract error format: every error is JSON {"error": CODE, "message": text} (REQ-14)."""

from __future__ import annotations

from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    resp = JSONResponse(status_code=status, content={"error": code, "message": message})
    return resp


def field_code(field: str) -> str:
    """INVALID_<FIELD> in upper snake case, following the contract's INVALID_DECISION example."""
    out = []
    for ch in field:
        if ch.isupper():
            out.append("_")
        out.append(ch.upper())
    return "INVALID_" + "".join(out)


def invalid(field: str, reason: str) -> ApiError:
    return ApiError(400, field_code(field), f"{field} {reason}")


def not_found(what: str, ident: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{what} {ident} does not exist")


def not_implemented(operation: str) -> ApiError:
    return ApiError(501, "NOT_IMPLEMENTED", f"{operation} is scheduled for a later phase")
