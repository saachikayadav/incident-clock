"""AC-01 Create/Retrieve Incidents (REQ-01, REQ-14)."""

from __future__ import annotations

import httpx
from conftest import conforms, parse_ts, valid_incident


def test_ac01_create_returns_201_with_id_and_open_status(api: httpx.Client) -> None:
    r = api.post("/incidents", json=valid_incident())
    assert r.status_code == 201, r.text
    body = r.json()
    conforms("IncidentCreated", body)
    assert body["status"] == "OPEN"
    assert body["incidentId"]


def test_ac01_get_returns_identical_values(api: httpx.Client) -> None:
    sent = valid_incident()
    incident_id = api.post("/incidents", json=sent).json()["incidentId"]

    r = api.get(f"/incidents/{incident_id}")
    assert r.status_code == 200, r.text
    got = r.json()
    conforms("Incident", got)
    assert got["incidentId"] == incident_id
    assert got["title"] == sent["title"]
    assert got["description"] == sent["description"]
    assert got["reporterName"] == sent["reporterName"]
    assert got["status"] == "OPEN"
    # Same instant, re-expressed in UTC (REQ-14).
    assert parse_ts(got["discoveredAt"]) == parse_ts(sent["discoveredAt"])
    assert got["discoveredAt"].endswith("Z")
    assert got["evidence"] == []
    assert got["currentDecision"] is None
    assert got["filing"] is None


def test_ac01_each_incident_gets_a_unique_id(api: httpx.Client) -> None:
    ids = {api.post("/incidents", json=valid_incident(title=f"Incident {i}")).json()["incidentId"] for i in range(5)}
    assert len(ids) == 5


def test_ac01_utc_offset_input_round_trips(api: httpx.Client) -> None:
    """Boundary: 'Z' and '+05:30' offsets are both RFC 3339 and must be accepted and normalized."""
    for ts in ("2025-09-22T18:30:00Z", "2025-09-23T00:00:00+05:30"):
        r = api.post("/incidents", json=valid_incident(discoveredAt=ts))
        assert r.status_code == 201, (ts, r.text)
        got = api.get(f"/incidents/{r.json()['incidentId']}").json()
        assert parse_ts(got["discoveredAt"]) == parse_ts(ts)
        assert got["discoveredAt"].endswith("Z")
