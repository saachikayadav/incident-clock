"""Request-body validation for the common interface (REQ-02, REQ-03, REQ-14).

Validation is explicit rather than delegated to framework defaults so that:
  * every failure is 400 (FastAPI's default is 422 - Phase 2 risk 2),
  * the error names the offending field in both code and message,
  * RFC 3339 timestamps *must* carry an offset (Python/Pydantic accept naive ones).
Fields are checked in contract order; the first failure is reported.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .config import MAX_LEN
from .errors import ApiError, invalid

# RFC 3339 section 5.6 date-time: full-date "T" full-time, offset mandatory.
_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$")

EVIDENCE_CATEGORIES = ("TECHNICAL", "BUSINESS_IMPACT", "LEGAL", "OTHER")


def parse_json_object(raw: bytes) -> dict[str, Any]:
    if not raw.strip():
        raise ApiError(400, "INVALID_BODY", "request body must be a JSON object")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "INVALID_BODY", "request body is not valid JSON") from None
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_BODY", "request body must be a JSON object")
    return data


def parse_rfc3339(value: str) -> datetime | None:
    """Return an aware datetime, or None if `value` is not RFC 3339 with an offset."""
    if not _RFC3339.match(value):
        return None
    try:
        dt = datetime.fromisoformat(value.upper())
    except ValueError:
        return None
    if dt.tzinfo is None:  # unreachable given the regex; kept as a guard
        return None
    return dt


def _text(data: dict[str, Any], field: str) -> str:
    if field not in data or data[field] is None:
        raise invalid(field, "is required")
    value = data[field]
    if not isinstance(value, str):
        raise invalid(field, "must be a string")
    if not value.strip():
        raise invalid(field, "must not be empty")
    limit = MAX_LEN.get(field)
    if limit is not None and len(value) > limit:
        raise invalid(field, f"must be at most {limit} characters")
    return value


def _timestamp(data: dict[str, Any], field: str, *, now: datetime, allow_future: bool) -> datetime:
    if field not in data or data[field] is None:
        raise invalid(field, "is required")
    value = data[field]
    if not isinstance(value, str):
        raise invalid(field, "must be an RFC 3339 timestamp string")
    dt = parse_rfc3339(value)
    if dt is None:
        raise invalid(field, "must be an RFC 3339 timestamp with a timezone offset")
    if not allow_future and dt > now:
        raise invalid(field, "must not be in the future")
    return dt


@dataclass(frozen=True)
class IncidentInput:
    title: str
    description: str
    discovered_at: datetime
    reporter_name: str


@dataclass(frozen=True)
class EvidenceInput:
    category: str
    summary: str
    source: str
    collected_at: datetime


def validate_incident(data: dict[str, Any], now: datetime | None = None) -> IncidentInput:
    now = now or datetime.now(UTC)
    title = _text(data, "title")
    description = _text(data, "description")
    discovered_at = _timestamp(data, "discoveredAt", now=now, allow_future=False)
    reporter_name = _text(data, "reporterName")
    return IncidentInput(title, description, discovered_at, reporter_name)


def validate_evidence(data: dict[str, Any], now: datetime | None = None) -> EvidenceInput:
    now = now or datetime.now(UTC)
    if "category" not in data or data["category"] is None:
        raise invalid("category", "is required")
    category = data["category"]
    if category not in EVIDENCE_CATEGORIES:
        raise invalid("category", "must be one of " + ", ".join(EVIDENCE_CATEGORIES))
    summary = _text(data, "summary")
    source = _text(data, "source")
    # The contract restricts only discoveredAt/determinedAt from being in the
    # future; collectedAt has no such rule (docs/spec-issues.md, ISSUE-06).
    collected_at = _timestamp(data, "collectedAt", now=now, allow_future=True)
    return EvidenceInput(category, summary, source, collected_at)


def to_utc(dt: datetime) -> str:
    """Serialize as RFC 3339 in UTC with a 'Z' suffix (REQ-14)."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
