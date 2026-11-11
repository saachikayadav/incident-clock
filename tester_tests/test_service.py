"""Self-tests for the tester HTTP service, with the target replaced by an in-process fake.

The full suite against a real system runs in CI (job "tester end-to-end"); these tests
pin the tester's own contract: status codes, error sources, session state rules.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

TARGET = "https://target.example.edu/system"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("TARGETS", f'{{"{TARGET}": "k"}}')
    from tester import main

    # Keep wake-up/retry loops fast and offline: healthy target, tiny time budget.
    monkeypatch.setattr(main, "SETUP_TIMEOUT", 0.3)
    monkeypatch.setattr(main, "SETUP_RETRY_SECONDS", 0.05)
    monkeypatch.setattr(main, "WAKE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(
        httpx, "get", lambda url, **_: httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))
    )
    monkeypatch.setattr(
        main,
        "_run_suite",
        lambda session, key: (
            {
                "session_id": session.session_id,
                "target_url": session.target_url,
                "results": [],
                "coverage": {},
                "summary": {},
            },
            None,
        ),
    )
    return TestClient(main.create_app())


def fake_post(status: int, body: Any = None, exc: Exception | None = None) -> Any:
    def _post(url: str, json: dict[str, Any], **_: Any) -> httpx.Response:
        if exc:
            raise exc
        payload = body if body is not None else {"session_id": json["session_id"]}
        return httpx.Response(status, json=payload, request=httpx.Request("POST", url))

    return _post


def test_setup_run_report_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(201))
    r = client.post("/test/setup", json={"target_url": TARGET + "/"})
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert client.get("/test/report", params={"session_id": sid}).status_code == 409  # not run yet
    run = client.post("/test/run", json={"session_id": sid})
    assert run.status_code == 200 and run.json()["session_id"] == sid
    assert client.get("/test/report", params={"session_id": sid}).json() == run.json()
    again = client.post("/test/run", json={"session_id": sid})
    assert again.status_code == 409 and again.json()["source"] == "tester"


def test_unregistered_target_never_receives_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(httpx, "post", lambda url, **_: called.append(url))
    r = client.post("/test/setup", json={"target_url": "https://attacker.example.com"})
    assert r.status_code == 400 and r.json()["source"] == "tester" and called == []


def test_system_setup_error_forwarded_with_same_status_and_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(500, {"message": "Could not initialize.", "source": "system"}))
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 500 and r.json() == {"message": "Could not initialize.", "source": "system"}


def test_unreachable_target_is_communication_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(0, exc=httpx.ConnectError("refused")))
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 500 and r.json()["source"] == "communication"


def test_mismatched_session_id_from_target_is_system_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(201, {"session_id": "something-else"}))
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 500 and r.json()["source"] == "system"


@pytest.mark.parametrize(
    "method,path,body,params,status",
    [
        ("POST", "/test/setup", {}, None, 400),
        ("POST", "/test/run", {}, None, 400),
        ("POST", "/test/run", {"session_id": "unknown"}, None, 404),
        ("GET", "/test/report", None, None, 400),
        ("GET", "/test/report", None, {"session_id": "unknown"}, 404),
    ],
)
def test_error_codes_and_body_shape(
    client: TestClient, method: str, path: str, body: Any, params: Any, status: int
) -> None:
    r = client.request(method, path, json=body, params=params)
    assert r.status_code == status
    assert r.json()["message"] and r.json()["source"] == "tester"


def test_failed_setup_does_not_create_session(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(409, {"message": "exists", "source": "system"}))
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 409
    assert "session_id" not in r.json()


def sequence_post(responses: list[httpx.Response | None]) -> tuple[Any, list[str]]:
    """Fake POST that returns the given responses in order (None = echo a 201 with the session_id)."""
    calls: list[str] = []

    def _post(url: str, json: dict[str, Any], **_: Any) -> httpx.Response:
        calls.append(url)
        r = responses[min(len(calls), len(responses)) - 1]
        if r is None:
            return httpx.Response(201, json={"session_id": json["session_id"]}, request=httpx.Request("POST", url))
        return r

    return _post, calls


def gateway(status: int = 502) -> httpx.Response:
    return httpx.Response(status, text="<html>Bad Gateway</html>", request=httpx.Request("POST", "https://x"))


def test_gateway_error_while_target_wakes_is_retried(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    post, calls = sequence_post([gateway(502), gateway(503), None])
    monkeypatch.setattr(httpx, "post", post)
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 201 and r.json()["session_id"]
    assert len(calls) == 3


def test_persistent_gateway_error_is_communication_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    post, calls = sequence_post([gateway(502)])
    monkeypatch.setattr(httpx, "post", post)
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 500
    assert r.json()["source"] == "communication" and "HTTP 502" in r.json()["message"]
    assert len(calls) > 1


def test_system_json_503_is_forwarded_not_retried(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"message": "Database unavailable.", "source": "system"}
    post, calls = sequence_post([httpx.Response(503, json=body, request=httpx.Request("POST", "https://x"))])
    monkeypatch.setattr(httpx, "post", post)
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 503 and r.json() == body and len(calls) == 1


def test_setup_waits_for_health_before_posting(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    health = iter([503, 503, 200])
    events: list[str] = []

    def _get(url: str, **_: Any) -> httpx.Response:
        events.append("health")
        return httpx.Response(next(health, 200), json={}, request=httpx.Request("GET", url))

    post, _ = sequence_post([None])

    def _post(url: str, **kw: Any) -> httpx.Response:
        events.append("setup")
        response: httpx.Response = post(url, **kw)
        return response

    monkeypatch.setattr(httpx, "get", _get)
    monkeypatch.setattr(httpx, "post", _post)
    r = client.post("/test/setup", json={"target_url": TARGET})
    assert r.status_code == 201
    assert events == ["health", "health", "health", "setup"]
