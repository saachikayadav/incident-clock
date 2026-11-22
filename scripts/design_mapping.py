"""Generate docs/design-requirements.md from tester/design_requirements.json.

The JSON is the single source for coverage.model; this table is the human-readable mapping the
report's basis links to. `--check` exits 1 if the committed table is stale (used by CI).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tester" / "design_requirements.json"
OUT = ROOT / "docs" / "design-requirements.md"


def render() -> str:
    d = json.loads(SRC.read_text())
    lines = [
        "# Design requirements and the tests that evaluate them (coverage.model)",
        "",
        f"Design version: **{d['design_version']}**. Generated from `tester/design_requirements.json` by",
        "`scripts/design_mapping.py`; do not edit by hand. The tester reports `coverage.model` from this",
        "mapping only when it tests this team's own system (`OWN_SYSTEM_URLS`). A requirement counts as",
        "covered when at least one mapped test was executed and evaluated (pass or fail).",
        "",
        "| ID | Model | Design requirement | Tests |",
        "|---|---|---|---|",
    ]
    for r in d["requirements"]:
        tests = "<br>".join(f"`{t}`" for t in r["tests"])
        lines.append(f"| {r['id']} | {r['model']} | {r['text']} | {tests} |")
    lines += ["", f"Total: {len(d['requirements'])} design requirements.", ""]
    return "\n".join(lines)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is stale; run python scripts/design_mapping.py")
            return 1
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
