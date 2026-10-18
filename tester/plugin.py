"""pytest plugin used by the tester service to record one outcome per planned test.

Loaded with ``-p tester.plugin`` in the subprocess that runs the contract suite.
Writes, under $TESTER_OUT_DIR:
  planned.json   - node IDs of every collected (planned) test, in execution order
  results.jsonl  - one line per finished test, appended as soon as it finishes, so
                   a crash or timeout still leaves every completed outcome on disk

Outcome mapping (course testing interface):
  pass   - test passed
  fail   - the target answered and the answer differs from expectations
           (AssertionError, or a body that is not the JSON the contract requires)
  error  - evaluation was prevented; ``source`` says where:
             system        - unexpected 5xx from the target, or a precondition request
                             (POST /reset in fixture setup) did not succeed
             communication - timeout / connection failure, no response to evaluate
             unknown       - any other exception (cannot attribute reliably)
  skip   - not executed (pytest skip), with the skip reason as the message
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

OUT = Path(os.environ.get("TESTER_OUT_DIR", "."))
_partial: dict[str, dict[str, Any]] = {}


def test_id(nodeid: str) -> str:
    return nodeid.removeprefix("tests/")


def _first_line(text: str, limit: int = 400) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line[:limit]


def classify(excinfo: pytest.ExceptionInfo[BaseException], when: str) -> tuple[str, str | None, str]:
    """Return (outcome, source, message) for an exception raised in a test phase."""
    from conftest import TargetSystemError  # the suite's conftest, importable once collected

    exc = excinfo.value
    text = _first_line(str(exc)) or type(exc).__name__
    if isinstance(exc, TargetSystemError):
        return "error", "system", f"Target internal error: {text}"
    if isinstance(exc, httpx.TimeoutException):
        return "error", "communication", f"Request timed out; no response to evaluate ({type(exc).__name__})."
    if isinstance(exc, httpx.TransportError):
        return "error", "communication", f"Could not reach the target: {type(exc).__name__}: {text}"
    if isinstance(exc, AssertionError):
        if when == "setup":
            return "error", "system", f"Precondition failed before the test could run: {text}"
        return "fail", None, text
    if isinstance(exc, json.JSONDecodeError):
        return "fail", None, "Response body is not valid JSON."
    return "error", "unknown", f"{type(exc).__name__}: {text}"


def pytest_collection_finish(session: pytest.Session) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "planned.json").write_text(json.dumps([test_id(item.nodeid) for item in session.items]))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Any:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    entry = _partial.setdefault(item.nodeid, {"test_id": test_id(item.nodeid)})
    if report.skipped:
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        entry.setdefault("result", ("skip", None, _first_line(reason.removeprefix("Skipped: ")) or "Skipped."))
    elif report.failed and call.excinfo is not None:
        entry.setdefault("result", classify(call.excinfo, call.when))
    elif report.passed and call.when == "call":
        doc = _first_line(item.function.__doc__ or "") if isinstance(item, pytest.Function) else ""
        name = item.name.removeprefix("test_").replace("_", " ")
        entry.setdefault("result", ("pass", None, f"Behaved as expected: {doc or name}"))
    if call.when == "teardown":  # pytest always runs teardown, even after a setup skip/failure
        _finish(item.nodeid)


def _finish(nodeid: str) -> None:
    entry = _partial.pop(nodeid, None)
    if entry is None:
        return
    outcome, source, message = entry.get("result", ("error", "unknown", "No outcome was recorded."))
    line: dict[str, Any] = {"test_id": entry["test_id"], "outcome": outcome, "message": message or outcome}
    if source is not None:
        line["source"] = source
    with (OUT / "results.jsonl").open("a") as fh:
        fh.write(json.dumps(line) + "\n")
