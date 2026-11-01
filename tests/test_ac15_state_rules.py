"""AC-15 State Rules (REQ-08), plus the REQ-07 405 checks for the Phase 4 resources (part of AC-08)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from conftest import FIXTURES_P4, assert_error, decide, decision_body, incident_with_evidence, material_incident

AC11: dict[str, Any] = FIXTURES_P4["AC11"]


def _snapshot(api: httpx.Client, incident_id: str) -> dict[str, Any]:
    r = api.get(f"/incidents/{incident_id}")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def _filed_incident(api: httpx.Client) -> str:
    incident_id = material_incident(api)
    r = api.post(f"/incidents/{incident_id}/filing", json=AC11["onTimeFiling"])
    assert r.status_code == 201, r.text
    return incident_id


# ---- AC-15: the three cases named in the criterion -----------------------------


def test_ac15_new_decision_while_material_pending_filing_409(api: httpx.Client) -> None:
    incident_id = material_incident(api)
    before = _snapshot(api, incident_id)
    evidence_id = before["currentDecision"]["evidenceIds"][0]
    body = decision_body([evidence_id], base="notMaterialDecision", determinedAt="2025-09-30T10:00:00-04:00")
    assert_error(api.post(f"/incidents/{incident_id}/decisions", json=body), 409)
    assert _snapshot(api, incident_id) == before


def test_ac15_decision_while_filed_409(api: httpx.Client) -> None:
    incident_id = _filed_incident(api)
    before = _snapshot(api, incident_id)
    evidence_id = before["currentDecision"]["evidenceIds"][0]
    assert_error(api.post(f"/incidents/{incident_id}/decisions", json=decision_body([evidence_id])), 409)
    assert _snapshot(api, incident_id) == before


def test_ac15_filing_while_open_409(api: httpx.Client) -> None:
    incident_id, _ = incident_with_evidence(api)
    before = _snapshot(api, incident_id)
    assert_error(api.post(f"/incidents/{incident_id}/filing", json=AC11["onTimeFiling"]), 409)
    after = _snapshot(api, incident_id)
    assert after == before
    assert after["status"] == "OPEN" and after["filing"] is None


# ---- AC-15: the remaining REQ-08 filing rule ------------------------------------


def test_ac15_filing_while_not_material_409(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, base="notMaterialDecision")
    before = _snapshot(api, incident_id)
    assert_error(api.post(f"/incidents/{incident_id}/filing", json=AC11["onTimeFiling"]), 409)
    assert _snapshot(api, incident_id) == before


def test_ac15_second_filing_while_filed_409(api: httpx.Client) -> None:
    incident_id = _filed_incident(api)
    before = _snapshot(api, incident_id)
    assert_error(api.post(f"/incidents/{incident_id}/filing", json=AC11["lateFiling"]), 409)
    assert _snapshot(api, incident_id) == before


def test_ac15_evidence_still_accepted_after_filing(api: httpx.Client) -> None:
    """Section 5.1: evidence can be added regardless of status; state rules do not block it."""
    incident_id = _filed_incident(api)
    r = api.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "category": "LEGAL",
            "summary": "Outside counsel memo.",
            "source": "Counsel",
            "collectedAt": "2025-10-07T09:00:00-04:00",
        },
    )
    assert r.status_code == 201, r.text
    assert _snapshot(api, incident_id)["status"] == "FILED"


@pytest.mark.provisional
def test_ac15_new_decision_after_not_material_allowed(api: httpx.Client) -> None:
    """REQ-08 lists no 409 for a new decision on a NOT_MATERIAL incident (ISSUE-20)."""
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, base="notMaterialDecision")
    created = decide(api, incident_id, evidence_id, determinedAt="2025-10-01T10:00:00-04:00")
    assert created["status"] == "MATERIAL_PENDING_FILING"
    assert created["deadline"] == "2025-10-07"


@pytest.mark.provisional
def test_ac15_invalid_body_on_filed_incident_is_400_not_409(api: httpx.Client) -> None:
    """Check order 400 before 409 (Model 4 as implemented; ISSUE-03)."""
    incident_id = _filed_incident(api)
    assert_error(api.post(f"/incidents/{incident_id}/decisions", json={"decision": "BOGUS"}), 400)


# ---- REQ-07 for decisions and filings (Phase 4 portion of AC-08) ----------------


@pytest.mark.provisional
@pytest.mark.parametrize("suffix", ["/decisions", "/filing"])
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_req07_decision_and_filing_edit_or_delete_405(api: httpx.Client, method: str, suffix: str) -> None:
    """No item URLs exist for decisions/filings (ISSUE-05); edits on the collection paths are 405."""
    incident_id = _filed_incident(api)
    before = _snapshot(api, incident_id)
    assert_error(api.request(method, f"/incidents/{incident_id}{suffix}", json={}), 405)
    assert _snapshot(api, incident_id) == before


@pytest.mark.provisional
def test_ac15_foreign_evidence_on_pending_incident_is_400_not_409(api: httpx.Client) -> None:
    """Every 400 precedes 409 (Model 4; ISSUE-03), including the evidence-ownership check."""
    incident_id = material_incident(api)
    _, foreign = incident_with_evidence(api)
    before = _snapshot(api, incident_id)
    assert_error(api.post(f"/incidents/{incident_id}/decisions", json=decision_body([foreign])), 400)
    assert _snapshot(api, incident_id) == before
