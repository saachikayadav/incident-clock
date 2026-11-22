"""Model coverage mapping (tester/design_requirements.json) stays consistent with the suite.

Fails CI when a design requirement has no test, names a test that does not exist, or the
generated docs/design-requirements.md is stale: the drift these checks exist to catch.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from tester import reporting

ROOT = Path(__file__).resolve().parent.parent
TEST_NAMES = {
    m.group(1) for f in (ROOT / "tests").glob("test_*.py") for m in re.finditer(r"^def (test_\w+)", f.read_text(), re.M)
}


def test_every_design_requirement_has_existing_tests() -> None:
    design = reporting.load_design()
    ids = [r["id"] for r in design["requirements"]]
    assert ids == [f"DR-{n:02d}" for n in range(1, len(ids) + 1)], "IDs must be DR-01..DR-NN in order"
    for r in design["requirements"]:
        assert r["text"].strip() and r["model"] in {"M1", "M2", "M3", "M4", "A1", "T1"}, r["id"]
        assert r["tests"], f"{r['id']} has no test"
        missing = [t for t in r["tests"] if t not in TEST_NAMES]
        assert not missing, f"{r['id']} maps to tests that do not exist: {missing}"


def test_model_coverage_counts_evaluated_requirements_only() -> None:
    design = {
        "design_version": "v-test",
        "mapping_url": "https://example/{version}/map.md",
        "requirements": [
            {"id": "DR-01", "model": "M1", "text": "a", "tests": ["test_a"]},
            {"id": "DR-02", "model": "M1", "text": "b", "tests": ["test_b", "test_c"]},
            {"id": "DR-03", "model": "M1", "text": "c", "tests": ["test_d"]},
        ],
    }
    results = [
        {"test_id": "test_x.py::test_a[1]", "outcome": "fail", "message": "m"},  # evaluated: counts
        {"test_id": "test_x.py::test_c", "outcome": "pass", "message": "m"},
        {"test_id": "test_x.py::test_d", "outcome": "skip", "message": "m"},  # not evaluated
    ]
    m = reporting.model_coverage(results, "abc123", design)
    assert (m["covered"], m["total"]) == (2, 3)
    assert "https://example/abc123/map.md" in m["basis"] and "DR-01, DR-02" in m["basis"]
    assert reporting.model_coverage(results, "dev", design)["basis"].count("/main/") == 1


def test_generated_mapping_doc_is_current() -> None:
    out = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "design_mapping.py"), "--check"], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stdout + out.stderr
