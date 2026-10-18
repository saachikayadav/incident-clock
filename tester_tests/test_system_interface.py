"""Our system's course testing endpoints (POST /test/setup, GET /test/report).

Runs against a live system: SYSTEM_BASE_URL=http://127.0.0.1:8000 API_KEY=... pytest tester_tests
Skipped when SYSTEM_BASE_URL is unset. Not part of the cross-team test plan (tests/),
which covers only the pod contract.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import httpx
import pytest

BASE = os.environ.get("SYSTEM_BASE_URL", "").rstrip("/")
KEY = os.environ.get("API_KEY", "")
pytestmark = pytest.mark.skipif(not BASE, reason="SYSTEM_BASE_URL not set")


@pytest.fixture(scope="module")
def sys_api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE, headers={"X-API-Key": KEY}, timeout=60) as c:
        yield c


def _setup(c: httpx.Client, sid: str) -> httpx.Response:
    return c.post("/test/setup", json={"session_id": sid, "setup": {}})


def _error_shape(r: httpx.Response, status: int) -> None:
    assert r.status_code == status, r.text
    body = r.json()
    assert body["message"].strip() and body["source"] == "system"


def test_setup_returns_same_id_and_clears_project_data(sys_api: httpx.Client) -> None:
    created = sys_api.post(
        "/incidents",
        json={"title": "t", "description": "d", "discoveredAt": "2025-09-22T14:30:00Z", "reporterName": "r"},
    )
    assert created.status_code == 201
    sid = f"selftest-{uuid.uuid4()}"
    r = _setup(sys_api, sid)
    assert r.status_code == 201 and r.json() == {"session_id": sid}
    assert sys_api.get(f"/incidents/{created.json()['incidentId']}").status_code == 404


def test_reused_session_id_is_409_and_changes_nothing(sys_api: httpx.Client) -> None:
    sid = f"selftest-{uuid.uuid4()}"
    assert _setup(sys_api, sid).status_code == 201
    inc = sys_api.post(
        "/incidents",
        json={"title": "t", "description": "d", "discoveredAt": "2025-09-22T14:30:00Z", "reporterName": "r"},
    )
    _error_shape(_setup(sys_api, sid), 409)
    assert sys_api.get(f"/incidents/{inc.json()['incidentId']}").status_code == 200  # not wiped


def test_report_coverage_grows_with_project_requests(sys_api: httpx.Client) -> None:
    sid = f"selftest-{uuid.uuid4()}"
    assert _setup(sys_api, sid).status_code == 201
    before = sys_api.get("/test/report", params={"session_id": sid}).json()["coverage"]["code"]
    sys_api.post(
        "/incidents",
        json={"title": "", "description": "d", "discoveredAt": "2025-09-22T14:30:00Z", "reporterName": "r"},
    )
    after = sys_api.get("/test/report", params={"session_id": sid}).json()
    assert after["session_id"] == sid
    code = after["coverage"]["code"]
    assert code["basis"].strip()
    if code["covered"] is not None:  # instrumentation available
        assert 0 <= before["covered"] <= code["covered"] <= code["total"]
        assert code["covered"] > before["covered"]


def test_report_for_superseded_session_still_available(sys_api: httpx.Client) -> None:
    first, second = f"selftest-{uuid.uuid4()}", f"selftest-{uuid.uuid4()}"
    assert _setup(sys_api, first).status_code == 201
    assert _setup(sys_api, second).status_code == 201
    r = sys_api.get("/test/report", params={"session_id": first})
    assert r.status_code == 200 and r.json()["session_id"] == first


@pytest.mark.parametrize(
    "body",
    [{}, {"session_id": ""}, {"session_id": 7}, {"session_id": "x", "setup": []}],
    ids=["missing", "empty", "not-string", "setup-not-object"],
)
def test_setup_invalid_requests_400(sys_api: httpx.Client, body: dict[str, object]) -> None:
    _error_shape(sys_api.post("/test/setup", json=body), 400)


def test_report_unknown_or_missing_session(sys_api: httpx.Client) -> None:
    _error_shape(sys_api.get("/test/report", params={"session_id": "never-created"}), 404)
    _error_shape(sys_api.get("/test/report"), 400)


def test_test_endpoints_require_key() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as anon:
        _error_shape(anon.post("/test/setup", json={"session_id": "x"}), 401)
        _error_shape(anon.get("/test/report", params={"session_id": "x"}), 401)
