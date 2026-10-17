"""AC-14 Authentication (REQ-13), AC-16 Reset/Persistence/Performance (REQ-14, REQ-15),
REQ-07 append-only behavior available in Phase 3 (part of AC-08)."""

from __future__ import annotations

import os
import time

import httpx
import pytest
from conftest import BASE_URL, assert_error, conforms, create_incident, valid_evidence, valid_incident

# ---- AC-14 -----------------------------------------------------------------

PROTECTED = [
    ("POST", "/incidents"),
    ("GET", "/incidents/INC-001"),
    ("POST", "/incidents/INC-001/evidence"),
    ("POST", "/reset"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_ac14_missing_key_401(anon: httpx.Client, method: str, path: str) -> None:
    assert_error(anon.request(method, path, json={}), 401)


@pytest.mark.parametrize("method,path", PROTECTED)
def test_ac14_wrong_key_401(anon: httpx.Client, method: str, path: str) -> None:
    assert_error(anon.request(method, path, json={}, headers={"X-API-Key": "wrong-key"}), 401)


def test_ac14_valid_key_succeeds(api: httpx.Client) -> None:
    assert api.post("/incidents", json=valid_incident()).status_code == 201


def test_ac14_health_needs_no_key(anon: httpx.Client) -> None:
    r = anon.get("/health")
    assert r.status_code == 200
    conforms("StatusMessage", r.json())


def test_ac14_unauthorized_request_changes_nothing(api: httpx.Client, anon: httpx.Client) -> None:
    incident_id = create_incident(api)
    anon.post(f"/incidents/{incident_id}/evidence", json=valid_evidence(), headers={"X-API-Key": "nope"})
    anon.post("/reset")
    got = api.get(f"/incidents/{incident_id}")
    assert got.status_code == 200 and got.json()["evidence"] == []


def test_ac14_served_over_https() -> None:
    """Inspection half of AC-14 automated for deployed targets."""
    if not BASE_URL.startswith("https://"):
        pytest.skip(f"target {BASE_URL} is not a deployed HTTPS URL")
    insecure = BASE_URL.replace("https://", "http://", 1)
    with httpx.Client(timeout=30, follow_redirects=False) as c:
        r = c.get(insecure + "/health")
    # Plain HTTP must not serve the API directly: either redirect to HTTPS or refuse.
    assert r.status_code in (301, 302, 307, 308), f"plain HTTP returned {r.status_code}"


# ---- REQ-07 (AC-08, Phase 3 portion) ----------------------------------------


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_req07_incident_edit_or_delete_405(api: httpx.Client, method: str) -> None:
    incident_id = create_incident(api)
    assert_error(api.request(method, f"/incidents/{incident_id}", json={"title": "edited"}), 405)
    got = api.get(f"/incidents/{incident_id}").json()
    assert got["title"] == valid_incident()["title"]


# ---- AC-16 -----------------------------------------------------------------


def test_ac16_reset_clears_all_records(api: httpx.Client) -> None:
    ids = [create_incident(api, title=f"I{i}") for i in range(3)]
    r = api.post("/reset")
    assert r.status_code == 200
    conforms("StatusMessage", r.json())
    for incident_id in ids:
        assert_error(api.get(f"/incidents/{incident_id}"), 404)


def test_ac16_latency_95pct_under_1s_with_100_incidents(api: httpx.Client) -> None:
    """100 incidents loaded, then 200 timed requests; >=95% must finish within 1 s."""
    if os.environ.get("SKIP_PERF") == "1":
        pytest.skip("SKIP_PERF=1")
    ids = [create_incident(api, title=f"Load {i}") for i in range(100)]
    api.get("/health")  # wake a sleeping host before timing
    latencies = []
    for i in range(200):
        incident_id = ids[i % len(ids)]
        start = time.perf_counter()
        if i % 2 == 0:
            r = api.get(f"/incidents/{incident_id}")
            ok = r.status_code == 200
        else:
            r = api.post(f"/incidents/{incident_id}/evidence", json=valid_evidence())
            ok = r.status_code == 201
        latencies.append(time.perf_counter() - start)
        assert ok, r.text
    within = sum(1 for t in latencies if t <= 1.0) / len(latencies)
    p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1]
    print(f"\nAC-16 latency: {within:.1%} within 1s, p95={p95 * 1000:.0f} ms, max={max(latencies) * 1000:.0f} ms")
    assert within >= 0.95
