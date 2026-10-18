"""Black-box contract test harness.

The suite talks to a deployed service over HTTP only, so it runs unchanged
against any team's implementation:

    BASE_URL=https://other-team.example.com API_KEY=<shared test key> pytest

Nothing here imports the application. Every test starts from POST /reset
(Phase 2, Q5.3).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
TIMEOUT = float(os.environ.get("TEST_TIMEOUT_SECONDS", "30"))
# Set by the deployed tester service: one JSON line per request (method, path, status),
# used to compute component coverage. Unset for ordinary local/CI runs.
TRACE_FILE = os.environ.get("TESTER_TRACE_FILE")


class TargetSystemError(Exception):
    """The target answered with an unexpected 5xx: an internal failure, not a contract mismatch.

    501 is excluded because it is the documented reply for operations scheduled for later
    phases (docs/spec-issues.md ISSUE-09); tests evaluate it like any other response.
    """


def _on_response(response: httpx.Response) -> None:
    if TRACE_FILE:
        with open(TRACE_FILE, "a") as fh:
            fh.write(
                json.dumps(
                    {
                        "method": response.request.method,
                        "path": response.request.url.path,
                        "status": response.status_code,
                    }
                )
                + "\n"
            )
    if response.status_code >= 500 and response.status_code != 501:
        response.read()
        raise TargetSystemError(
            f"{response.request.method} {response.request.url.path} returned {response.status_code}: "
            f"{response.text[:300]}"
        )


HOOKS = {"response": [_on_response]}

CONTRACT = yaml.safe_load((Path(__file__).resolve().parent.parent / "openapi" / "contract.yaml").read_text())


def pytest_report_header(config: pytest.Config) -> str:
    return f"target BASE_URL={BASE_URL}  api_key={'set' if API_KEY else 'MISSING'}"


@pytest.fixture(scope="session")
def anon() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, event_hooks=HOOKS) as c:
        yield c


@pytest.fixture(scope="session")
def api(anon: httpx.Client) -> Iterator[httpx.Client]:
    if not API_KEY:
        pytest.exit("API_KEY environment variable is required", returncode=2)
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": API_KEY}, event_hooks=HOOKS) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("no_reset"):
        return
    api_client: httpx.Client = request.getfixturevalue("api")
    r = api_client.post("/reset")
    assert r.status_code == 200, f"POST /reset failed: {r.status_code} {r.text}"


# ---- contract helpers ------------------------------------------------------


def conforms(schema_name: str, body: Any) -> None:
    """Assert `body` matches components.schemas[schema_name] in openapi/contract.yaml."""
    schema = {"$ref": f"#/components/schemas/{schema_name}", "components": CONTRACT["components"]}
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(body),
        key=lambda e: list(e.path),
    )
    assert not errors, f"{schema_name} violation: " + "; ".join(
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
    )


def assert_error(resp: httpx.Response, status: int) -> dict[str, Any]:
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {resp.text}"
    body: dict[str, Any] = resp.json()
    conforms("Error", body)
    return body


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---- synthetic fixture data -----------------------------------------------

FIXTURES = yaml.safe_load((Path(__file__).resolve().parent.parent / "fixtures" / "phase3.json").read_text())


def valid_incident(**overrides: Any) -> dict[str, Any]:
    body = dict(FIXTURES["validIncident"])
    body.update(overrides)
    return body


def valid_evidence(**overrides: Any) -> dict[str, Any]:
    body = dict(FIXTURES["validEvidence"])
    body.update(overrides)
    return body


def create_incident(api: httpx.Client, **overrides: Any) -> str:
    r = api.post("/incidents", json=valid_incident(**overrides))
    assert r.status_code == 201, r.text
    return str(r.json()["incidentId"])


def now_utc() -> datetime:
    return datetime.now(UTC)
