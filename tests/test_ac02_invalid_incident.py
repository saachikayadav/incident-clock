"""AC-02 Reject Invalid Incidents (REQ-02, REQ-14).

The error must be 400 with the contract error body and must name the bad field.
"Naming" is checked leniently (field name in message OR error code) so the test
holds for any implementation that follows the contract's {error, message} shape.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest
from conftest import FIXTURES, assert_error, now_utc, valid_incident

REQUIRED = ["title", "description", "discoveredAt", "reporterName"]


def names_field(body: dict[str, Any], field: str) -> bool:
    snake = "".join("_" + c if c.isupper() else c.upper() for c in field)
    return field.lower() in body["message"].lower() or snake in body["error"]


@pytest.mark.parametrize("case", FIXTURES["acceptance_AC02"], ids=lambda c: c["case"])
def test_ac02_pod_fixture_cases_rejected(api: httpx.Client, case: dict[str, Any]) -> None:
    body = assert_error(api.post("/incidents", json=case["body"]), 400)
    assert names_field(body, case["field"]), body


@pytest.mark.parametrize("field", REQUIRED)
def test_ac02_missing_required_field(api: httpx.Client, field: str) -> None:
    payload = valid_incident()
    del payload[field]
    body = assert_error(api.post("/incidents", json=payload), 400)
    assert names_field(body, field), body


@pytest.mark.parametrize("field", ["title", "description", "reporterName"])
@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "whitespace"])
def test_ac02_empty_text_field(api: httpx.Client, field: str, value: str) -> None:
    body = assert_error(api.post("/incidents", json=valid_incident(**{field: value})), 400)
    assert names_field(body, field), body


@pytest.mark.parametrize("field", REQUIRED)
def test_ac02_null_field(api: httpx.Client, field: str) -> None:
    body = assert_error(api.post("/incidents", json=valid_incident(**{field: None})), 400)
    assert names_field(body, field), body


@pytest.mark.parametrize("field", ["title", "description", "reporterName"])
def test_ac02_wrong_type(api: httpx.Client, field: str) -> None:
    body = assert_error(api.post("/incidents", json=valid_incident(**{field: 12345})), 400)
    assert names_field(body, field), body


@pytest.mark.parametrize(
    "ts",
    [
        "2025-09-22T14:30:00",  # no offset
        "2025-09-22 14:30:00",  # no offset, space separator
        "2025-09-22",  # date only
        "22/09/2025 14:30 -04:00",  # not RFC 3339
        "2025-13-01T00:00:00Z",  # invalid month
        "2025-09-22T14:30:00+0400",  # offset missing colon
        "not-a-date",
    ],
)
def test_ac02_malformed_discovered_at(api: httpx.Client, ts: str) -> None:
    body = assert_error(api.post("/incidents", json=valid_incident(discoveredAt=ts)), 400)
    assert names_field(body, "discoveredAt"), body


def test_ac02_future_discovered_at_boundary(api: httpx.Client) -> None:
    """One hour ahead is rejected; one minute in the past is accepted."""
    future = (now_utc() + timedelta(hours=1)).isoformat()
    assert_error(api.post("/incidents", json=valid_incident(discoveredAt=future)), 400)
    past = (now_utc() - timedelta(minutes=1)).isoformat()
    assert api.post("/incidents", json=valid_incident(discoveredAt=past)).status_code == 201


@pytest.mark.parametrize(
    "raw",
    [b"", b"{not json", b"[]", b'"a string"', b"null"],
    ids=["empty", "malformed", "array", "string", "null"],
)
def test_ac02_body_not_a_json_object(api: httpx.Client, raw: bytes) -> None:
    assert_error(api.post("/incidents", content=raw, headers={"Content-Type": "application/json"}), 400)


def test_ac02_rejected_request_creates_nothing(api: httpx.Client) -> None:
    """AC-02 also requires 'incident count unchanged'. Contract v1.0 has no list
    operation, so a black-box client cannot count incidents (spec ISSUE-01)."""
    pytest.skip("AC-02 count check needs a list operation absent from contract v1.0 (ISSUE-01)")


# ---- provisional: values not yet fixed by the pod (ISSUE-02) ---------------


@pytest.mark.provisional
@pytest.mark.parametrize("field,limit", [("title", 200), ("description", 5000)])
def test_ac02_length_limit_boundary(api: httpx.Client, field: str, limit: int) -> None:
    """Proposed limits; contract v1.0 says only 'maximum length agreed by both teams'."""
    ok = api.post("/incidents", json=valid_incident(**{field: "x" * limit}))
    assert ok.status_code == 201, ok.text
    body = assert_error(api.post("/incidents", json=valid_incident(**{field: "x" * (limit + 1)})), 400)
    assert names_field(body, field), body


@pytest.mark.provisional
def test_ac02_unknown_extra_fields_ignored(api: httpx.Client) -> None:
    """Contract v1.0 is silent on unknown fields; this team ignores them (ISSUE-07)."""
    payload = valid_incident()
    payload["severity"] = "HIGH"
    r = api.post("/incidents", content=json.dumps(payload), headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
