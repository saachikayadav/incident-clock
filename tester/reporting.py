"""Build the suite report: results in planned order plus code/component/system coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ---- component coverage ------------------------------------------------------
# Components = the operations of the pod's common interface contract v1.0
# (openapi/contract.yaml). Proposed definition pending pod agreement (spec ISSUE-11).
OPERATIONS: list[tuple[str, str, re.Pattern[str]]] = [
    ("GET", "/health", re.compile(r"^/health$")),
    ("POST", "/incidents", re.compile(r"^/incidents$")),
    ("GET", "/incidents/{incidentId}", re.compile(r"^/incidents/[^/]+$")),
    ("POST", "/incidents/{incidentId}/evidence", re.compile(r"^/incidents/[^/]+/evidence$")),
    ("POST", "/incidents/{incidentId}/decisions", re.compile(r"^/incidents/[^/]+/decisions$")),
    ("POST", "/incidents/{incidentId}/corrections", re.compile(r"^/incidents/[^/]+/corrections$")),
    ("GET", "/incidents/{incidentId}/deadline-status", re.compile(r"^/incidents/[^/]+/deadline-status$")),
    ("POST", "/incidents/{incidentId}/filing", re.compile(r"^/incidents/[^/]+/filing$")),
    ("GET", "/incidents/{incidentId}/timeline", re.compile(r"^/incidents/[^/]+/timeline$")),
    ("POST", "/reset", re.compile(r"^/reset$")),
]
# Responses that never reach an operation's own logic: auth rejection, unknown
# incident, method not allowed, operation not implemented yet.
_NOT_EXERCISED = {401, 404, 405, 501}

# ---- system coverage ---------------------------------------------------------
# Acceptance criteria AC-01..AC-16 from the pod specification (Phase 2, section 4.1).
ACCEPTANCE_CRITERIA = [f"AC-{n:02d}" for n in range(1, 17)]
_EXTRA_AC = {"req07": "AC-08"}  # REQ-07 tests are the Phase 3 portion of AC-08


def acs_for(test_id: str) -> set[str]:
    """Map a test to the acceptance criteria it evaluates, from its function name."""
    func = test_id.split("::")[-1].split("[")[0]
    found = {f"AC-{int(n):02d}" for n in re.findall(r"_ac(\d{2})", "_" + func.removeprefix("test"))}
    for key, ac in _EXTRA_AC.items():
        if f"_{key}_" in func + "_":
            found.add(ac)
    return found


def component_coverage(trace_file: Path) -> dict[str, Any]:
    exercised: set[str] = set()
    if trace_file.exists():
        for line in trace_file.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("status") in _NOT_EXERCISED:
                continue
            for method, template, pattern in OPERATIONS:
                if rec.get("method") == method and pattern.match(rec.get("path", "")):
                    exercised.add(f"{method} {template}")
    return {
        "covered": len(exercised),
        "total": len(OPERATIONS),
        "basis": (
            "Operations of the pod common interface contract v1.0 (proposed component list, pending pod "
            "agreement); an operation counts when at least one request reached its own logic, i.e. "
            "received a response other than 401, 404, 405 or 501. Exercised: "
            + (", ".join(sorted(exercised)) or "none")
        ),
    }


def system_coverage(results: list[dict[str, Any]]) -> dict[str, Any]:
    covered: set[str] = set()
    for r in results:
        if r["outcome"] in ("pass", "fail"):
            covered |= acs_for(r["test_id"])
    covered &= set(ACCEPTANCE_CRITERIA)
    return {
        "covered": len(covered),
        "total": len(ACCEPTANCE_CRITERIA),
        "basis": (
            "Acceptance criteria AC-01..AC-16 in the pod specification (Phase 2, section 4.1); a criterion "
            "counts when at least one of its tests was executed and evaluated (pass or fail). AC-08 is counted "
            "from its REQ-07 portion only. Covered: " + (", ".join(sorted(covered)) or "none")
        ),
    }


def code_coverage(system_report: dict[str, Any] | None, problem: str | None) -> dict[str, Any]:
    if system_report is not None:
        code = system_report.get("coverage", {}).get("code") if isinstance(system_report, dict) else None
        if isinstance(code, dict) and isinstance(code.get("basis"), str) and code["basis"].strip():
            cov, tot = code.get("covered"), code.get("total")
            both_null = cov is None and tot is None
            ints_ok = isinstance(cov, int) and isinstance(tot, int) and 0 <= cov <= tot
            if both_null or ints_ok:
                return {"covered": cov, "total": tot, "basis": code["basis"]}
        problem = "target /test/report returned malformed coverage.code"
    return {"covered": None, "total": None, "basis": f"Source lines; not available from the target: {problem}"}


def assemble_results(
    planned: list[str], recorded: list[dict[str, Any]], aborted: bool, abort_message: str
) -> list[dict[str, Any]]:
    """Every planned test exactly once, in planned order."""
    by_id = {r["test_id"]: r for r in recorded}
    results: list[dict[str, Any]] = []
    interrupted_marked = False
    for tid in planned:
        if tid in by_id:
            results.append(by_id[tid])
        elif aborted and not interrupted_marked:
            results.append(
                {
                    "test_id": tid,
                    "outcome": "error",
                    "source": "tester",
                    "message": f"Prevented by tester abort: {abort_message}",
                }
            )
            interrupted_marked = True
        elif aborted:
            results.append({"test_id": tid, "outcome": "skip", "message": "Not executed: the tester aborted."})
        else:
            results.append(
                {
                    "test_id": tid,
                    "outcome": "error",
                    "source": "tester",
                    "message": "The tester recorded no outcome for this planned test.",
                }
            )
    return results


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(results), "pass": 0, "fail": 0, "error": 0, "skip": 0}
    for r in results:
        counts[r["outcome"]] += 1
    return counts
