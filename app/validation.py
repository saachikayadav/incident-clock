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


def parse_json_object(raw: bytes, source: str | None = None) -> dict[str, Any]:
    if not raw.strip():
        raise ApiError(400, "INVALID_BODY", "request body must be a JSON object", source)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "INVALID_BODY", "request body is not valid JSON", source) from None
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_BODY", "request body must be a JSON object", source)
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


DECISION_VALUES = ("MATERIAL", "NOT_MATERIAL")


@dataclass(frozen=True)
class DecisionInput:
    decision: str
    determined_at: datetime
    decided_by: str
    rationale: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class FilingInput:
    filed_at: datetime
    accession_number: str


def validate_decision(data: dict[str, Any], *, discovered_at: datetime, now: datetime | None = None) -> DecisionInput:
    """REQ-04/REQ-05 field rules. Evidence ownership is checked by the caller against the store."""
    now = now or datetime.now(UTC)
    if "decision" not in data or data["decision"] is None:
        raise invalid("decision", "is required")
    decision = data["decision"]
    if decision not in DECISION_VALUES:
        # Wording follows the contract's invalid-input example (Phase 2 section 5.2).
        raise invalid("decision", "must be MATERIAL or NOT_MATERIAL")
    determined_at = _timestamp(data, "determinedAt", now=now, allow_future=False)
    if determined_at < discovered_at:
        raise invalid("determinedAt", "must not be before the incident's discoveredAt")
    decided_by = _text(data, "decidedBy")
    rationale = _text(data, "rationale")
    if "evidenceIds" not in data or data["evidenceIds"] is None:
        raise invalid("evidenceIds", "is required")
    ids = data["evidenceIds"]
    if not isinstance(ids, list) or not ids:
        raise invalid("evidenceIds", "must be a non-empty array of evidence IDs")
    if not all(isinstance(i, str) and i.strip() for i in ids):
        raise invalid("evidenceIds", "must contain only non-empty strings")
    if len(set(ids)) != len(ids):
        raise invalid("evidenceIds", "must not contain duplicates")
    return DecisionInput(decision, determined_at, decided_by, rationale, tuple(ids))


def validate_filing(data: dict[str, Any], now: datetime | None = None) -> FilingInput:
    """REQ-11 field rules. The contract states no future/order rule for filedAt (ISSUE-18)."""
    now = now or datetime.now(UTC)
    filed_at = _timestamp(data, "filedAt", now=now, allow_future=True)
    accession_number = _text(data, "accessionNumber")
    return FilingInput(filed_at, accession_number)


def parse_as_of(raw: str | None) -> datetime | None:
    """Optional `as_of` query value (REQ-10). None if absent; 400 if malformed.

    A '+' offset sent unencoded in a query string arrives as a space; it is restored so
    `as_of=2025-10-06T12:00:00+00:00` works whether or not the client encoded it.
    """
    if raw is None:
        return None
    value = raw.strip()
    if len(value) >= 6 and value[-6] == " ":
        value = value[:-6] + "+" + value[-5:]
    dt = parse_rfc3339(value)
    if dt is None:
        raise invalid("as_of", "must be an RFC 3339 timestamp with a timezone offset")
    return dt
