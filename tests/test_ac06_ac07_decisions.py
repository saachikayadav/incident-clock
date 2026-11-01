"""AC-06 Record/Validate Materiality Decision (REQ-04, REQ-05) and
AC-07 No Automated Materiality Decision (REQ-04, automated half)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from conftest import (
    FIXTURES_P4,
    add_evidence,
    assert_error,
    conforms,
    create_incident,
    decide,
    decision_body,
    incident_with_evidence,
    parse_ts,
)

# ---- AC-06 -----------------------------------------------------------------


def test_ac06_complete_decision_stored_and_status_material_pending(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    sent = decision_body([evidence_id])
    r = api.post(f"/incidents/{incident_id}/decisions", json=sent)
    assert r.status_code == 201, r.text
    created = r.json()
    conforms("DecisionCreated", created)
    assert created["status"] == "MATERIAL_PENDING_FILING"

    got = api.get(f"/incidents/{incident_id}").json()
    conforms("Incident", got)
    assert got["status"] == "MATERIAL_PENDING_FILING"
    current = got["currentDecision"]
    assert current["decisionId"] == created["decisionId"]
    assert current["decision"] == "MATERIAL"
    assert parse_ts(current["determinedAt"]) == parse_ts(sent["determinedAt"])
    assert current["determinedAt"].endswith("Z")
    assert current["decidedBy"] == sent["decidedBy"]
    assert current["rationale"] == sent["rationale"]
    assert current["evidenceIds"] == [evidence_id]
    assert current["deadline"] == created["deadline"]


def test_ac06_determination_before_discovery_rejected_and_not_stored(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)  # discovered 2025-09-22T14:30-04:00
    body = assert_error(
        api.post(
            f"/incidents/{incident_id}/decisions",
            json=decision_body([evidence_id], determinedAt="2025-09-22T14:29:59-04:00"),
        ),
        400,
    )
    assert "determinedat" in body["message"].lower() or "DETERMINED_AT" in body["error"], body
    got = api.get(f"/incidents/{incident_id}").json()
    assert got["status"] == "OPEN"
    assert got["currentDecision"] is None


def test_ac06_determination_equal_to_discovery_accepted(api: httpx.Client) -> None:
    """Boundary: REQ-05 rejects only 'before' discovery; the same instant in another offset is allowed."""
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt="2025-09-22T18:30:00Z")


def test_ac06_contract_invalid_decision_example(api: httpx.Client) -> None:
    """Phase 2 section 5.2 invalid-input example: the one error code the contract fixes."""
    incident_id, evidence_id = incident_with_evidence(api)
    body = assert_error(
        api.post(
            f"/incidents/{incident_id}/decisions",
            json=decision_body([evidence_id], decision="PROBABLY_MATERIAL", rationale="More review may be needed."),
        ),
        400,
    )
    assert body["error"] == "INVALID_DECISION"


def test_ac06_not_material_decision_has_no_deadline(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    created = decide(api, incident_id, evidence_id, base="notMaterialDecision")
    conforms("DecisionCreated", created)
    assert created["status"] == "NOT_MATERIAL"
    assert created["deadline"] is None
    got = api.get(f"/incidents/{incident_id}").json()
    assert got["status"] == "NOT_MATERIAL"
    assert got["currentDecision"]["deadline"] is None


def test_ac06_multiple_evidence_ids_kept_in_order(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    ids = [add_evidence(api, incident_id) for _ in range(3)]
    sent = list(reversed(ids))
    r = api.post(f"/incidents/{incident_id}/decisions", json=decision_body(sent))
    assert r.status_code == 201, r.text
    assert api.get(f"/incidents/{incident_id}").json()["currentDecision"]["evidenceIds"] == sent


def test_ac06_evidence_from_another_incident_rejected(api: httpx.Client) -> None:
    a, _ = incident_with_evidence(api)
    _, other_evidence = incident_with_evidence(api)
    assert_error(api.post(f"/incidents/{a}/decisions", json=decision_body([other_evidence])), 400)
    assert api.get(f"/incidents/{a}").json()["currentDecision"] is None


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"evidenceIds": ["EVD-999"]}, "evidenceIds"),
        ({"evidenceIds": []}, "evidenceIds"),
        ({"evidenceIds": "EVD-001"}, "evidenceIds"),
        ({"decision": "material"}, "decision"),
        ({"decision": None}, "decision"),
        ({"determinedAt": "2025-09-29T10:00:00"}, "determinedAt"),
        ({"determinedAt": "2099-01-01T00:00:00Z"}, "determinedAt"),
        ({"determinedAt": "Sept 29 2025"}, "determinedAt"),
        ({"decidedBy": ""}, "decidedBy"),
        ({"rationale": "   "}, "rationale"),
    ],
)
def test_ac06_invalid_decision_rejected_and_not_stored(
    api: httpx.Client, overrides: dict[str, Any], field: str
) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    body = assert_error(
        api.post(f"/incidents/{incident_id}/decisions", json=decision_body([evidence_id], **overrides)), 400
    )
    snake = "".join("_" + c if c.isupper() else c.upper() for c in field)
    assert field.lower() in body["message"].lower() or snake in body["error"], body
    got = api.get(f"/incidents/{incident_id}").json()
    assert got["status"] == "OPEN" and got["currentDecision"] is None


@pytest.mark.parametrize("missing", ["decision", "determinedAt", "decidedBy", "rationale", "evidenceIds"])
def test_ac06_missing_decision_field_rejected(api: httpx.Client, missing: str) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    payload = decision_body([evidence_id])
    del payload[missing]
    assert_error(api.post(f"/incidents/{incident_id}/decisions", json=payload), 400)
    assert api.get(f"/incidents/{incident_id}").json()["currentDecision"] is None


@pytest.mark.provisional
def test_ac06_duplicate_evidence_ids_rejected(api: httpx.Client) -> None:
    """Contract is silent on duplicates (docs/spec-issues.md ISSUE-21); we reject them."""
    incident_id, evidence_id = incident_with_evidence(api)
    assert_error(api.post(f"/incidents/{incident_id}/decisions", json=decision_body([evidence_id, evidence_id])), 400)


@pytest.mark.provisional
def test_ac06_unknown_incident_checked_before_body(api: httpx.Client) -> None:
    """Check order 404 before 400 (Model 4; ISSUE-03)."""
    assert_error(api.post("/incidents/INC-DOES-NOT-EXIST/decisions", json={"decision": "BOGUS"}), 404)


# ---- AC-07 -----------------------------------------------------------------


def test_ac07_severe_evidence_without_decision_stays_open(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    r = api.post(f"/incidents/{incident_id}/evidence", json=FIXTURES_P4["severeEvidence"])
    assert r.status_code == 201, r.text
    for _ in range(3):  # also LEGAL and TECHNICAL items: volume of evidence must not trigger anything
        add_evidence(api, incident_id, category="LEGAL")

    got = api.get(f"/incidents/{incident_id}").json()
    conforms("Incident", got)
    assert got["status"] == "OPEN"
    assert got["currentDecision"] is None

    status = api.get(f"/incidents/{incident_id}/deadline-status", params={"as_of": "2025-12-31T12:00:00Z"})
    assert status.status_code == 200, status.text
    conforms("DeadlineStatus", status.json())
    assert status.json()["status"] == "NOT_APPLICABLE"
    assert status.json()["deadline"] is None
