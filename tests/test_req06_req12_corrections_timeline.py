"""Phase 5: corrections (REQ-06, with the REQ-08 correction rules and REQ-07) and the timeline
with evidence summary (REQ-12): AC-08 (correction-history part), AC-12 and AC-13 from the
Phase 2 report, section 4.1, plus further REQ-06/REQ-12 cases.

Expected values are derived by hand from the requirement text and the Phase 4 fixtures, never
from the implementation. The incident fixture is discovered Mon 2025-09-22 (Eastern Time).
  * AC-09 determination Mon 2025-09-29 -> deadline Fri 2025-10-03.
  * Correction determined Fri 2025-10-10 -> deadline Fri 2025-10-17 (Columbus Day Mon 10-13
    skipped; the AC-10 fixture case).
  * Correction determined Wed 2025-10-01 -> deadline Tue 2025-10-07.
Tests of behaviour the pod has not fixed are marked provisional (docs/spec-issues.md).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from conftest import (
    FIXTURES,
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

AC11: dict[str, Any] = FIXTURES_P4["AC11"]
LATER = "2025-10-10T10:00:00-04:00"  # deadline 2025-10-17
EARLIER = "2025-10-01T10:00:00-04:00"  # deadline 2025-10-07


def correction_body(
    evidence_ids: list[str], corrects: str, base: str = "materialDecision", **overrides: Any
) -> dict[str, Any]:
    body = decision_body(evidence_ids, base, **overrides)
    body["correctsDecisionId"] = corrects
    return body


def correct(api: httpx.Client, incident_id: str, body: dict[str, Any]) -> dict[str, Any]:
    r = api.post(f"/incidents/{incident_id}/corrections", json=body)
    assert r.status_code == 201, r.text
    created: dict[str, Any] = r.json()
    conforms("DecisionCreated", created)
    return created


def snapshot(api: httpx.Client, incident_id: str) -> dict[str, Any]:
    r = api.get(f"/incidents/{incident_id}")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def timeline(api: httpx.Client, incident_id: str) -> dict[str, Any]:
    r = api.get(f"/incidents/{incident_id}/timeline")
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    conforms("Timeline", body)
    return body


def material(api: httpx.Client) -> tuple[str, str, str]:
    """(incident, evidence, decision) with a MATERIAL decision: MATERIAL_PENDING_FILING, deadline 10-03."""
    incident_id, evidence_id = incident_with_evidence(api)
    return incident_id, evidence_id, str(decide(api, incident_id, evidence_id)["decisionId"])


def history(api: httpx.Client, incident_id: str) -> list[tuple[str, str]]:
    return [(e["eventType"], e["referenceId"]) for e in timeline(api, incident_id)["events"]]


# ---- REQ-06: a correction replaces the current decision -----------------------


def test_req06_correction_to_not_material_changes_status_and_clears_deadline(api: httpx.Client) -> None:
    incident_id, evidence_id, first = material(api)
    created = correct(api, incident_id, correction_body([evidence_id], first, base="notMaterialDecision"))
    assert (created["status"], created["deadline"]) == ("NOT_MATERIAL", None)
    assert created["decisionId"] != first

    got = snapshot(api, incident_id)
    conforms("Incident", got)
    assert got["status"] == "NOT_MATERIAL"
    assert got["currentDecision"]["decisionId"] == created["decisionId"]
    assert (got["currentDecision"]["decision"], got["currentDecision"]["deadline"]) == ("NOT_MATERIAL", None)

    r = api.get(f"/incidents/{incident_id}/deadline-status", params={"as_of": AC11["overdueAsOf"]})
    assert r.status_code == 200 and r.json()["status"] == "NOT_APPLICABLE"


def test_req06_correction_to_material_uses_new_determination_for_deadline(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    first = decide(api, incident_id, evidence_id, base="notMaterialDecision")["decisionId"]
    created = correct(api, incident_id, correction_body([evidence_id], first, determinedAt=EARLIER))
    assert (created["status"], created["deadline"]) == ("MATERIAL_PENDING_FILING", "2025-10-07")
    got = snapshot(api, incident_id)
    assert got["status"] == "MATERIAL_PENDING_FILING"
    assert got["currentDecision"]["deadline"] == "2025-10-07"


def test_req06_corrected_deadline_drives_deadline_status(api: httpx.Client) -> None:
    """Before the correction the AC-11 as_of is OVERDUE by 1; after it, PENDING with 8 left."""
    incident_id, evidence_id, first = material(api)
    url = f"/incidents/{incident_id}/deadline-status"
    before = api.get(url, params={"as_of": AC11["overdueAsOf"]}).json()
    assert (before["status"], before["deadline"], before["businessDays"]) == ("OVERDUE", "2025-10-03", 1)

    created = correct(api, incident_id, correction_body([evidence_id], first, determinedAt=LATER))
    assert created["deadline"] == "2025-10-17"
    after = api.get(url, params={"as_of": AC11["overdueAsOf"]}).json()
    conforms("DeadlineStatus", after)
    assert (after["status"], after["deadline"], after["businessDays"]) == ("PENDING", "2025-10-17", 8)


def test_req06_filing_after_correction_is_judged_against_corrected_deadline(api: httpx.Client) -> None:
    """AC-11's late filing (Mon 10-06) is LATE against 10-03 but ON_TIME against the corrected 10-17."""
    incident_id, evidence_id, first = material(api)
    correct(api, incident_id, correction_body([evidence_id], first, determinedAt=LATER))
    r = api.post(f"/incidents/{incident_id}/filing", json=AC11["lateFiling"])
    assert r.status_code == 201, r.text
    assert (r.json()["timeliness"], r.json()["businessDaysLate"]) == ("ON_TIME", 0)


def test_ac08_correction_keeps_old_decision_in_history(api: httpx.Client) -> None:
    """AC-08: after a correction the new decision is current and the old one stays in the history
    as the superseded DECISION_RECORDED entry. Contract v1.0 has no decision-history read path,
    so the timeline is the history (ISSUE-10); the 405 steps are the test_req07_* tests (ISSUE-05)."""
    incident_id, evidence_id, first = material(api)
    second = correct(api, incident_id, correction_body([evidence_id], first, base="notMaterialDecision"))
    assert snapshot(api, incident_id)["currentDecision"]["decisionId"] == second["decisionId"]
    assert history(api, incident_id) == [
        ("INCIDENT_CREATED", incident_id),
        ("EVIDENCE_ADDED", evidence_id),
        ("DECISION_RECORDED", first),
        ("DECISION_CORRECTED", second["decisionId"]),
    ]


def test_req06_corrections_chain_latest_is_current(api: httpx.Client) -> None:
    incident_id, evidence_id, first = material(api)
    second = correct(api, incident_id, correction_body([evidence_id], first, base="notMaterialDecision"))
    third = correct(api, incident_id, correction_body([evidence_id], second["decisionId"], determinedAt=LATER))
    got = snapshot(api, incident_id)
    assert got["currentDecision"]["decisionId"] == third["decisionId"]
    assert (got["status"], got["currentDecision"]["deadline"]) == ("MATERIAL_PENDING_FILING", "2025-10-17")
    events = [t for t, _ in history(api, incident_id)]
    assert events.count("DECISION_RECORDED") == 1 and events.count("DECISION_CORRECTED") == 2


def test_req06_correction_may_cite_new_evidence(api: httpx.Client) -> None:
    incident_id, evidence_id, first = material(api)
    newer = add_evidence(api, incident_id, **FIXTURES["businessImpactEvidence"])
    correct(api, incident_id, correction_body([evidence_id, newer], first, determinedAt=LATER))
    assert snapshot(api, incident_id)["currentDecision"]["evidenceIds"] == [evidence_id, newer]


# ---- REQ-08: correction state rules (409, nothing changes) ----------------------


def test_req08_correction_while_filed_409(api: httpx.Client) -> None:
    incident_id, evidence_id, first = material(api)
    assert api.post(f"/incidents/{incident_id}/filing", json=AC11["onTimeFiling"]).status_code == 201
    before, events = snapshot(api, incident_id), history(api, incident_id)
    body = correction_body([evidence_id], first, base="notMaterialDecision")
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=body), 409)
    assert snapshot(api, incident_id) == before
    assert history(api, incident_id) == events


@pytest.mark.provisional
def test_req06_correcting_a_superseded_decision_409(api: httpx.Client) -> None:
    """REQ-06: a correction 'points to the current decision'. Pointing at one that was already
    corrected is a stale state, answered 409 like the REQ-08 rules (ISSUE-24)."""
    incident_id, evidence_id, first = material(api)
    correct(api, incident_id, correction_body([evidence_id], first, base="notMaterialDecision"))
    before = snapshot(api, incident_id)
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=correction_body([evidence_id], first)), 409)
    assert snapshot(api, incident_id) == before


# ---- REQ-06 / REQ-05: invalid corrections (400, nothing stored) -----------------


def test_req06_corrects_unknown_decision_400(api: httpx.Client) -> None:
    incident_id, evidence_id, _ = material(api)
    before = snapshot(api, incident_id)
    body = correction_body([evidence_id], "DEC-999")
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=body), 400)
    assert snapshot(api, incident_id) == before


def test_req06_corrects_decision_of_another_incident_400(api: httpx.Client) -> None:
    incident_id, evidence_id, _ = material(api)
    _, _, foreign = material(api)
    before = snapshot(api, incident_id)
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=correction_body([evidence_id], foreign)), 400)
    assert snapshot(api, incident_id) == before


def test_req06_correction_on_open_incident_400(api: httpx.Client) -> None:
    """With no decision there is nothing to correct; any correctsDecisionId is unknown here."""
    incident_id, evidence_id = incident_with_evidence(api)
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=correction_body([evidence_id], "DEC-001")), 400)
    assert snapshot(api, incident_id)["status"] == "OPEN"


@pytest.mark.parametrize(
    "case,change",
    [
        ("missing correctsDecisionId", {"correctsDecisionId": None}),
        ("empty correctsDecisionId", {"correctsDecisionId": " "}),
        ("bad decision value", {"decision": "PROBABLY"}),
        ("determination in the future", {"determinedAt": "2099-01-01T00:00:00Z"}),
        ("determination before discovery", {"determinedAt": "2025-09-21T10:00:00-04:00"}),
        ("timestamp without offset", {"determinedAt": "2025-10-10T10:00:00"}),
        ("empty evidenceIds", {"evidenceIds": []}),
        ("empty rationale", {"rationale": ""}),
    ],
)
def test_req06_invalid_correction_rejected_and_not_stored(api: httpx.Client, case: str, change: dict[str, Any]) -> None:
    incident_id, evidence_id, first = material(api)
    before, events = snapshot(api, incident_id), history(api, incident_id)
    body = correction_body([evidence_id], first, determinedAt=LATER)
    body.update(change)
    if change.get("correctsDecisionId", "") is None:
        del body["correctsDecisionId"]
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=body), 400)
    assert snapshot(api, incident_id) == before, case
    assert history(api, incident_id) == events, case


def test_req06_correction_citing_foreign_evidence_400(api: httpx.Client) -> None:
    incident_id, _, first = material(api)
    _, foreign_evidence = incident_with_evidence(api)
    before = snapshot(api, incident_id)
    body = correction_body([foreign_evidence], first)
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json=body), 400)
    assert snapshot(api, incident_id) == before


@pytest.mark.provisional
def test_req06_invalid_body_on_filed_incident_is_400_not_409(api: httpx.Client) -> None:
    """Every 400 precedes every 409 (Model 4; ISSUE-03)."""
    incident_id, _, _ = material(api)
    assert api.post(f"/incidents/{incident_id}/filing", json=AC11["onTimeFiling"]).status_code == 201
    assert_error(api.post(f"/incidents/{incident_id}/corrections", json={"decision": "BOGUS"}), 400)


@pytest.mark.provisional
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_req07_corrections_edit_or_delete_405(api: httpx.Client, method: str) -> None:
    """No item URL exists for a correction (ISSUE-05); edits on the collection path are 405."""
    incident_id, evidence_id, first = material(api)
    correct(api, incident_id, correction_body([evidence_id], first, determinedAt=LATER))
    before = snapshot(api, incident_id)
    assert_error(api.request(method, f"/incidents/{incident_id}/corrections", json={}), 405)
    assert snapshot(api, incident_id) == before


# ---- REQ-12: timeline and evidence summary --------------------------------------


def test_ac12_five_events_in_recorded_order(api: httpx.Client) -> None:
    """AC-12: creation, evidence, decision, correction and filing, returned in recorded order
    with the contract's labels."""
    incident_id, evidence_id, first = material(api)
    second = correct(api, incident_id, correction_body([evidence_id], first, determinedAt=LATER))
    r = api.post(f"/incidents/{incident_id}/filing", json=AC11["onTimeFiling"])
    assert r.status_code == 201, r.text
    events = timeline(api, incident_id)["events"]
    assert [(e["eventType"], e["referenceId"]) for e in events] == [
        ("INCIDENT_CREATED", incident_id),
        ("EVIDENCE_ADDED", evidence_id),
        ("DECISION_RECORDED", first),
        ("DECISION_CORRECTED", second["decisionId"]),
        ("FILING_RECORDED", r.json()["filingId"]),
    ]
    times = [parse_ts(e["recordedAt"]) for e in events]
    assert times == sorted(times)


def test_ac13_evidence_summary(api: httpx.Client) -> None:
    """AC-13: discovered Sep 22 2025, 2 TECHNICAL + 1 BUSINESS_IMPACT, determined Sep 29 2025:
    counts 2/1/0/0 and 7 days from discovery to determination. Discovery is 14:30 and
    determination 10:00 ET, so 7 means whole calendar days (6.8 days elapsed)."""
    incident_id = create_incident(api)
    technical = [add_evidence(api, incident_id, **item) for item in FIXTURES["threeTechnicalEvidence"][:2]]
    add_evidence(api, incident_id, **FIXTURES["businessImpactEvidence"])
    decide(api, incident_id, technical[0])
    t = timeline(api, incident_id)
    assert t["evidenceCounts"] == {"technical": 2, "businessImpact": 1, "legal": 0, "other": 0}
    assert t["discoveryToDeterminationDays"] == 7
    stored = snapshot(api, incident_id)
    assert len(stored["evidence"]) == 3


def test_req12_new_incident_timeline(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    t = timeline(api, incident_id)
    assert t["incidentId"] == incident_id
    assert [(e["eventType"], e["referenceId"]) for e in t["events"]] == [("INCIDENT_CREATED", incident_id)]
    assert t["evidenceCounts"] == {"technical": 0, "businessImpact": 0, "legal": 0, "other": 0}
    assert t["discoveryToDeterminationDays"] is None


def test_req12_full_lifecycle_events_in_recorded_order(api: httpx.Client) -> None:
    incident_id, ev1, first = material(api)
    ev2 = add_evidence(api, incident_id, **FIXTURES["businessImpactEvidence"])
    second = correct(api, incident_id, correction_body([ev1, ev2], first, determinedAt=LATER))
    r = api.post(f"/incidents/{incident_id}/filing", json=AC11["lateFiling"])
    assert r.status_code == 201, r.text
    ev3 = add_evidence(api, incident_id, category="LEGAL", summary="Counsel memo.", source="Counsel")

    t = timeline(api, incident_id)
    assert [(e["eventType"], e["referenceId"]) for e in t["events"]] == [
        ("INCIDENT_CREATED", incident_id),
        ("EVIDENCE_ADDED", ev1),
        ("DECISION_RECORDED", first),
        ("EVIDENCE_ADDED", ev2),
        ("DECISION_CORRECTED", second["decisionId"]),
        ("FILING_RECORDED", r.json()["filingId"]),
        ("EVIDENCE_ADDED", ev3),
    ]
    times = [parse_ts(e["recordedAt"]) for e in t["events"]]
    assert times == sorted(times)
    assert t["evidenceCounts"] == {"technical": 1, "businessImpact": 1, "legal": 1, "other": 0}


def test_req12_evidence_counts_by_category(api: httpx.Client) -> None:
    incident_id = create_incident(api)
    for item in FIXTURES["threeTechnicalEvidence"]:
        add_evidence(api, incident_id, **item)
    add_evidence(api, incident_id, **FIXTURES["businessImpactEvidence"])
    add_evidence(api, incident_id, category="OTHER", summary="Press inquiry.", source="Comms")
    counts = timeline(api, incident_id)["evidenceCounts"]
    assert counts == {"technical": 3, "businessImpact": 1, "legal": 0, "other": 1}


def test_req12_timeline_is_read_only(api: httpx.Client) -> None:
    incident_id, _, _ = material(api)
    before = timeline(api, incident_id)
    timeline(api, incident_id)
    assert timeline(api, incident_id) == before


@pytest.mark.provisional
def test_req12_days_count_eastern_calendar_dates(api: httpx.Client) -> None:
    """Discovered Mon 2025-09-22 14:30 ET; determined Tue 2025-09-23 00:30 ET (04:30 UTC):
    1 day by Eastern dates although only 10 hours elapsed (REQ-09 day convention; ISSUE-25)."""
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt="2025-09-23T04:30:00Z")
    assert timeline(api, incident_id)["discoveryToDeterminationDays"] == 1


@pytest.mark.provisional
def test_req12_days_follow_the_current_decision(api: httpx.Client) -> None:
    """After a correction determined Fri 2025-10-10 the value is 18 days (ISSUE-25)."""
    incident_id, evidence_id, first = material(api)
    correct(api, incident_id, correction_body([evidence_id], first, determinedAt=LATER))
    assert timeline(api, incident_id)["discoveryToDeterminationDays"] == 18


@pytest.mark.provisional
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_req12_timeline_other_methods_405(api: httpx.Client, method: str) -> None:
    incident_id = create_incident(api)
    assert_error(api.request(method, f"/incidents/{incident_id}/timeline", json={}), 405)
