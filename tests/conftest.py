"""Black-box contract test harness.

The suite talks to a deployed service over HTTP only, so it runs unchanged
against any team's implementation:

    BASE_URL=https://other-team.example.com API_KEY=<shared test key> pytest

Nothing here imports the application. Every test starts from POST /reset
(Phase 2, Q5.3).
"""

from __future__ import annotations

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

CONTRACT = yaml.safe_load((Path(__file__).resolve().parent.parent / "openapi" / "contract.yaml").read_text())


def pytest_report_header(config: pytest.Config) -> str:
    return f"target BASE_URL={BASE_URL}  api_key={'set' if API_KEY else 'MISSING'}"


@pytest.fixture(scope="session")
def anon() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c


@pytest.fixture(scope="session")
def api(anon: httpx.Client) -> Iterator[httpx.Client]:
    if not API_KEY:
        pytest.exit("API_KEY environment variable is required", returncode=2)
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": API_KEY}) as c:
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
