"""AC-09 Standard Deadline, AC-10 Weekends and Holidays (REQ-09), and
AC-11 Overdue / On-Time / Late (REQ-10, REQ-11).

Expected dates are copied from the pod's acceptance criteria (Phase 2 Q4.1) and the
section 5.2 examples via fixtures/phase4.json; they were derived by hand from the
calendar, never from any implementation.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from conftest import FIXTURES_P4, assert_error, conforms, create_incident, decide, incident_with_evidence

AC10: list[dict[str, str]] = FIXTURES_P4["AC10"]
AC11: dict[str, Any] = FIXTURES_P4["AC11"]


def _deadline_everywhere(api: httpx.Client, determined_at: str) -> str:
    """Record a MATERIAL decision; the deadline must agree in all three places it is reported."""
    incident_id, evidence_id = incident_with_evidence(api)
    created = decide(api, incident_id, evidence_id, determinedAt=determined_at)
    stored = api.get(f"/incidents/{incident_id}").json()["currentDecision"]["deadline"]
    status = api.get(f"/incidents/{incident_id}/deadline-status", params={"as_of": determined_at}).json()
    assert created["deadline"] == stored == status["deadline"], (created, stored, status)
    return str(created["deadline"])


# ---- AC-09 -----------------------------------------------------------------


def test_ac09_monday_determination_due_friday(api: httpx.Client) -> None:
    case = FIXTURES_P4["AC09"]
    assert _deadline_everywhere(api, case["determinedAt"]) == case["deadline"] == "2025-10-03"


# ---- AC-10 -----------------------------------------------------------------


@pytest.mark.parametrize("case", AC10, ids=[c["case"] for c in AC10])
def test_ac10_weekend_and_holiday_deadlines(api: httpx.Client, case: dict[str, str]) -> None:
    assert _deadline_everywhere(api, case["determinedAt"]) == case["deadline"]


# REQ-09 counts from the Eastern Time date, not the UTC date (Phase 2 Q3.3).
@pytest.mark.parametrize(
    "determined_at,deadline",
    [
        # Mon Sep 29, 23:30 EDT is already Tue Sep 30 in UTC; ET day 0 is Monday.
        ("2025-09-30T03:30:00Z", "2025-10-03"),
        # Tue Sep 30, 00:30 EDT is still Mon Sep 29 in UTC; ET day 0 is Tuesday.
        ("2025-09-30T04:30:00Z", "2025-10-06"),
        # After DST ends (Nov 2, 2025) ET is UTC-5: Mon Nov 3, 23:30 EST; Veterans Day Nov 11 not reached.
        ("2025-11-04T04:30:00Z", "2025-11-07"),
        # Wed Nov 5 EST, crosses Veterans Day (Tue Nov 11).
        ("2025-11-05T15:00:00-05:00", "2025-11-12"),
    ],
)
def test_ac10_eastern_time_date_is_day_zero(api: httpx.Client, determined_at: str, deadline: str) -> None:
    assert _deadline_everywhere(api, determined_at) == deadline


# ---- AC-11 (deadline status, REQ-10) ----------------------------------------


def _status(api: httpx.Client, incident_id: str, as_of: str) -> dict[str, Any]:
    r = api.get(f"/incidents/{incident_id}/deadline-status", params={"as_of": as_of})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    conforms("DeadlineStatus", body)
    return body


def test_ac11_no_filing_overdue_one_business_day(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    body = _status(api, incident_id, AC11["overdueAsOf"])
    assert body == {"status": "OVERDUE", "deadline": "2025-10-03", "businessDays": 1}


@pytest.mark.parametrize(
    "as_of,expected",
    [
        ("2025-09-29T12:00:00-04:00", {"status": "PENDING", "deadline": "2025-10-03", "businessDays": 4}),
        ("2025-10-02T23:59:00-04:00", {"status": "PENDING", "deadline": "2025-10-03", "businessDays": 1}),
        ("2025-10-03T23:59:59-04:00", {"status": "PENDING", "deadline": "2025-10-03", "businessDays": 0}),
        # 00:30 EDT Saturday is already past the deadline date in ET.
        ("2025-10-04T04:30:00Z", {"status": "OVERDUE", "deadline": "2025-10-03", "businessDays": 1}),
        ("2025-10-14T12:00:00-04:00", {"status": "OVERDUE", "deadline": "2025-10-03", "businessDays": 6}),
    ],
)
def test_ac11_deadline_status_boundaries(api: httpx.Client, as_of: str, expected: dict[str, Any]) -> None:
    """Deadline Fri Oct 3, 2025. Oct 14 is 6 business days late because Columbus Day (Oct 13) is skipped."""
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    assert _status(api, incident_id, as_of) == expected


def test_ac11_contract_example_pending_one_day(api: httpx.Client) -> None:
    """Phase 2 section 5.2 example: decided 2026-09-22 15:00 EDT -> due 2026-09-28; 1 day left on Sep 25."""
    incident_id = create_incident(api, discoveredAt="2026-09-21T14:30:00-04:00")
    r = api.post(
        f"/incidents/{incident_id}/evidence",
        json={
            "category": "BUSINESS_IMPACT",
            "summary": "Order processing was unavailable for three hours.",
            "source": "Operations report",
            "collectedAt": "2026-09-21T17:30:00-04:00",
        },
    )
    evidence_id = r.json()["evidenceId"]
    created = decide(api, incident_id, evidence_id, determinedAt="2026-09-22T15:00:00-04:00")
    assert created["deadline"] == "2026-09-28"
    assert _status(api, incident_id, "2026-09-25T12:00:00Z") == {
        "status": "PENDING",
        "deadline": "2026-09-28",
        "businessDays": 1,
    }


def test_ac11_not_material_is_not_applicable(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, base="notMaterialDecision")
    assert _status(api, incident_id, AC11["overdueAsOf"]) == {
        "status": "NOT_APPLICABLE",
        "deadline": None,
        "businessDays": 0,
    }


def test_ac11_as_of_defaults_to_now(api: httpx.Client) -> None:
    """Without as_of the 2025 deadline is long past."""
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    r = api.get(f"/incidents/{incident_id}/deadline-status")
    assert r.status_code == 200, r.text
    conforms("DeadlineStatus", r.json())
    assert r.json()["status"] == "OVERDUE"
    assert r.json()["businessDays"] > 200


@pytest.mark.parametrize("as_of", ["2025-10-06", "2025-10-06T12:00:00", "yesterday", ""])
def test_ac11_invalid_as_of_400(api: httpx.Client, as_of: str) -> None:
    incident_id = create_incident(api)
    assert_error(api.get(f"/incidents/{incident_id}/deadline-status", params={"as_of": as_of}), 400)


# ---- AC-11 (filing timeliness, REQ-11) ---------------------------------------


def _file(api: httpx.Client, incident_id: str, filing: dict[str, str]) -> dict[str, Any]:
    r = api.post(f"/incidents/{incident_id}/filing", json=filing)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    conforms("FilingCreated", body)
    return body


def test_ac11_filed_on_deadline_on_time(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    created = _file(api, incident_id, AC11["onTimeFiling"])
    assert (created["status"], created["timeliness"], created["businessDaysLate"]) == ("FILED", "ON_TIME", 0)
    got = api.get(f"/incidents/{incident_id}").json()
    conforms("Incident", got)
    assert got["status"] == "FILED"
    assert got["filing"]["filingId"] == created["filingId"]
    assert got["filing"]["timeliness"] == "ON_TIME"
    assert got["filing"]["accessionNumber"] == AC11["onTimeFiling"]["accessionNumber"]
    assert got["filing"]["filedAt"].endswith("Z")


def test_ac11_filed_next_business_day_late_by_one(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    created = _file(api, incident_id, AC11["lateFiling"])
    assert (created["status"], created["timeliness"], created["businessDaysLate"]) == ("FILED", "LATE", 1)
    got = api.get(f"/incidents/{incident_id}").json()
    assert got["status"] == "FILED"
    assert (got["filing"]["timeliness"], got["filing"]["businessDaysLate"]) == ("LATE", 1)


def test_ac11_filed_incident_deadline_status_not_applicable(api: httpx.Client) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    _file(api, incident_id, AC11["lateFiling"])
    assert _status(api, incident_id, "2025-10-20T12:00:00Z")["status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"filedAt": "2025-10-03T16:00:00"},
        {"filedAt": None},
        {"accessionNumber": ""},
        {"accessionNumber": 1234},
    ],
)
def test_ac11_invalid_filing_rejected_and_not_stored(api: httpx.Client, overrides: dict[str, Any]) -> None:
    incident_id, evidence_id = incident_with_evidence(api)
    decide(api, incident_id, evidence_id, determinedAt=AC11["determinedAt"])
    payload = {**AC11["onTimeFiling"], **overrides}
    assert_error(api.post(f"/incidents/{incident_id}/filing", json=payload), 400)
    got = api.get(f"/incidents/{incident_id}").json()
    assert got["status"] == "MATERIAL_PENDING_FILING" and got["filing"] is None
