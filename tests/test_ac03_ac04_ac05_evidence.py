"""AC-03 Unknown Incident ID (REQ-14), AC-04 Attaching Evidence (REQ-03),
AC-05 Recording Business Impact (REQ-03)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from conftest import FIXTURES, assert_error, conforms, create_incident, parse_ts, valid_evidence

UNKNOWN = "INC-DOES-NOT-EXIST"


# ---- AC-03 -----------------------------------------------------------------


def test_ac03_get_unknown_incident_404(api: httpx.Client) -> None:
    assert_error(api.get(f"/incidents/{UNKNOWN}"), 404)


def test_ac03_post_evidence_unknown_incident_404(api: httpx.Client) -> None:
    assert_error(api.post(f"/incidents/{UNKNOWN}/evidence", json=valid_evidence()), 404)


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("POST", "/decisions"),
        ("POST", "/corrections"),
        ("GET", "/deadline-status"),
        ("POST", "/filing"),
        ("GET", "/timeline"),
    ],
)
def test_ac03_other_incident_operations_unknown_id_404(api: httpx.Client, method: str, suffix: str) -> None:
    """Every incident-scoped operation in contract v1.0 lists 404 for a missing incident.

    GETs carry no body (Cloud Run rejects GET with a body before the service sees it)."""
    assert_error(api.request(method, f"/incidents/{UNKNOWN}{suffix}", json=None if method == "GET" else {}), 404)


def test_ac03_reset_ids_do_not_resolve(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    assert api.post("/reset").status_code == 200
    assert_error(api.get(f"/incidents/{incident_id}"), 404)


@pytest.mark.provisional
def test_ac03_unknown_incident_checked_before_body(api: httpx.Client) -> None:
    """Check order 404 before 400 (Model 4 as proposed; ISSUE-03)."""
    assert_error(api.post(f"/incidents/{UNKNOWN}/evidence", json={"category": "BOGUS"}), 404)


# ---- AC-04 -----------------------------------------------------------------


def test_ac04_three_technical_items_linked_in_order(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    sent: list[dict[str, Any]] = FIXTURES["threeTechnicalEvidence"]
    ids = []
    for item in sent:
        r = api.post(f"/incidents/{incident_id}/evidence", json=item)
        assert r.status_code == 201, r.text
        conforms("EvidenceCreated", r.json())
        ids.append(r.json()["evidenceId"])
    assert len(set(ids)) == 3

    got = api.get(f"/incidents/{incident_id}").json()
    conforms("Incident", got)
    assert [e["evidenceId"] for e in got["evidence"]] == ids
    for stored, original in zip(got["evidence"], sent, strict=True):
        assert stored["category"] == "TECHNICAL"
        assert stored["source"] == original["source"]
        assert stored["summary"] == original["summary"]
        assert parse_ts(stored["collectedAt"]) == parse_ts(original["collectedAt"])
        assert stored["recordedAt"].endswith("Z")


def test_ac04_recorded_at_matches_create_response(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    created = api.post(f"/incidents/{incident_id}/evidence", json=valid_evidence()).json()
    stored = api.get(f"/incidents/{incident_id}").json()["evidence"][0]
    assert stored["evidenceId"] == created["evidenceId"]
    assert parse_ts(stored["recordedAt"]) == parse_ts(created["recordedAt"])


def test_ac04_evidence_not_leaked_across_incidents(api: httpx.Client) -> None:
    a, b = create_incident(api, title="A"), create_incident(api, title="B")
    api.post(f"/incidents/{a}/evidence", json=valid_evidence())
    assert api.get(f"/incidents/{b}").json()["evidence"] == []


@pytest.mark.parametrize("category", ["TECHNICAL", "BUSINESS_IMPACT", "LEGAL", "OTHER"])
def test_ac04_all_categories_accepted(api: httpx.Client, category: str) -> None:
    incident_id = create_incident(api)
    r = api.post(f"/incidents/{incident_id}/evidence", json=valid_evidence(category=category))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"category": "FINANCIAL"}, "category"),
        ({"category": "technical"}, "category"),
        ({"category": None}, "category"),
        ({"summary": ""}, "summary"),
        ({"source": "  "}, "source"),
        ({"collectedAt": "2025-09-22T15:05:00"}, "collectedAt"),
        ({"collectedAt": 1758567900}, "collectedAt"),
    ],
)
def test_ac04_invalid_evidence_rejected_and_not_stored(
    api: httpx.Client, overrides: dict[str, Any], field: str
) -> None:
    incident_id = create_incident(api)
    body = assert_error(api.post(f"/incidents/{incident_id}/evidence", json=valid_evidence(**overrides)), 400)
    snake = "".join("_" + c if c.isupper() else c.upper() for c in field)
    assert field.lower() in body["message"].lower() or snake in body["error"], body
    assert api.get(f"/incidents/{incident_id}").json()["evidence"] == []


@pytest.mark.parametrize("missing", ["category", "summary", "source", "collectedAt"])
def test_ac04_missing_evidence_field_rejected(api: httpx.Client, missing: str) -> None:
    incident_id = create_incident(api)
    payload = valid_evidence()
    del payload[missing]
    assert_error(api.post(f"/incidents/{incident_id}/evidence", json=payload), 400)


# ---- AC-05 -----------------------------------------------------------------


def test_ac05_business_impact_stored_unchanged(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    sent = FIXTURES["businessImpactEvidence"]
    created = api.post(f"/incidents/{incident_id}/evidence", json=sent)
    assert created.status_code == 201, created.text

    stored = api.get(f"/incidents/{incident_id}").json()["evidence"]
    assert len(stored) == 1
    item = stored[0]
    assert item["evidenceId"] == created.json()["evidenceId"]
    assert item["category"] == "BUSINESS_IMPACT"
    assert item["summary"] == sent["summary"]
    assert item["source"] == sent["source"]
    assert parse_ts(item["collectedAt"]) == parse_ts(sent["collectedAt"])
