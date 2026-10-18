"""Self-tests for the tester's report logic (not part of the cross-team test plan)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tester import reporting
from tester.main import TesterError, validate_target_url


def test_every_planned_test_appears_once_in_order() -> None:
    planned = ["a", "b", "c"]
    recorded = [
        {"test_id": "b", "outcome": "fail", "message": "x"},
        {"test_id": "a", "outcome": "pass", "message": "y"},
    ]
    out = reporting.assemble_results(planned, recorded, aborted=False, abort_message="")
    assert [r["test_id"] for r in out] == planned
    assert out[2] == {
        "test_id": "c",
        "outcome": "error",
        "source": "tester",
        "message": "The tester recorded no outcome for this planned test.",
    }


def test_abort_marks_interrupted_test_error_tester_and_rest_skip() -> None:
    planned = ["a", "b", "c", "d"]
    recorded = [{"test_id": "a", "outcome": "pass", "message": "ok"}]
    out = reporting.assemble_results(planned, recorded, aborted=True, abort_message="limit")
    assert [r["outcome"] for r in out] == ["pass", "error", "skip", "skip"]
    assert out[1]["source"] == "tester" and "limit" in out[1]["message"]
    assert all(r["message"] for r in out)


@pytest.mark.parametrize(
    "test_id,expected",
    [
        ("f.py::test_ac01_create", {"AC-01"}),
        ("f.py::test_ac04_all_categories_accepted[LEGAL]", {"AC-04"}),
        ("f.py::test_req07_incident_edit_or_delete_405[PUT]", {"AC-08"}),
        ("f.py::test_unrelated", set()),
    ],
)
def test_acceptance_criteria_mapping(test_id: str, expected: set[str]) -> None:
    assert reporting.acs_for(test_id) == expected


def test_system_coverage_counts_only_evaluated_tests() -> None:
    results = [
        {"test_id": "f::test_ac01_x", "outcome": "pass", "message": "m"},
        {"test_id": "f::test_ac02_x", "outcome": "fail", "message": "m"},
        {"test_id": "f::test_ac03_x", "outcome": "error", "source": "system", "message": "m"},
        {"test_id": "f::test_ac04_x", "outcome": "skip", "message": "m"},
    ]
    cov = reporting.system_coverage(results)
    assert (cov["covered"], cov["total"]) == (2, 16)


def test_component_coverage_ignores_unreached_operations(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    lines = [
        {"method": "POST", "path": "/incidents", "status": 201},
        {"method": "POST", "path": "/incidents/INC-9/decisions", "status": 501},  # not implemented
        {"method": "GET", "path": "/incidents/NOPE", "status": 404},  # unknown incident only
        {"method": "POST", "path": "/reset", "status": 401},  # auth rejected
        {"method": "PUT", "path": "/incidents/INC-1", "status": 405},  # not a contract op
    ]
    trace.write_text("\n".join(json.dumps(x) for x in lines))
    cov = reporting.component_coverage(trace)
    assert (cov["covered"], cov["total"]) == (1, 10)
    assert "POST /incidents" in cov["basis"]


@pytest.mark.parametrize(
    "body,problem,expected",
    [
        ({"coverage": {"code": {"covered": 5, "total": 10, "basis": "lines"}}}, None, (5, 10)),
        ({"coverage": {"code": {"covered": None, "total": None, "basis": "n/a"}}}, None, (None, None)),
        ({"coverage": {"code": {"covered": 11, "total": 10, "basis": "bad"}}}, None, (None, None)),
        ({"coverage": {"code": {"covered": 0, "total": 0, "basis": ""}}}, None, (None, None)),
        (None, "timeout", (None, None)),
    ],
)
def test_code_coverage_validation(body: dict | None, problem: str | None, expected: tuple) -> None:  # type: ignore[type-arg]
    cov = reporting.code_coverage(body, problem)
    assert (cov["covered"], cov["total"]) == expected
    assert cov["basis"].strip()


@pytest.mark.parametrize(
    "url",
    ["", "ftp://x", "https://x/system/test", "https://u:p@x", "https://x?a=1", "https://x#f", 42],
)
def test_invalid_target_urls_rejected(url: object) -> None:
    with pytest.raises(TesterError) as exc:
        validate_target_url(url)
    assert exc.value.status == 400 and exc.value.source == "tester"


def test_target_url_normalized() -> None:
    assert validate_target_url(" https://team-b.example.edu/system/ ") == "https://team-b.example.edu/system"
