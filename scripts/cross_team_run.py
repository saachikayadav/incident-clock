"""Drive a tester against a target system exactly as graders do, and keep the evidence.

  python scripts/cross_team_run.py --tester https://<tester-base> --target https://<system-base>

1. POST {tester}/test/setup {"target_url": target}   -> session_id
2. POST {tester}/test/run   {"session_id": ...}       -> suite report (or 500 -> GET /test/report)
3. Validates the report against openapi/tester.yaml (Report schema) and the course rules
   (each result once, unique non-empty test_id, non-empty message, source on every error,
   coverage counts null-or-0<=covered<=total with non-empty basis).
4. Saves reports/cross-team/<UTC timestamp>_<session>.json and prints a summary.

Exit code: 0 = well-formed report received; 1 = interface problem; 2 = --strict and some
test did not pass. Phase 3 only requires a well-formed report, so --strict is optional.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


def check_report(report: dict[str, Any]) -> list[str]:
    spec = yaml.safe_load((ROOT / "openapi" / "tester.yaml").read_text())
    schema = {"$ref": "#/components/schemas/Report", "components": spec["components"]}
    problems = [
        f"schema: {'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(schema).iter_errors(report)
    ]
    ids = [r.get("test_id") for r in report.get("results", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate test_id values")
    for r in report.get("results", []):
        if r.get("outcome") == "error" and not r.get("source"):
            problems.append(f"{r.get('test_id')}: error without source")
    for name, m in (report.get("coverage") or {}).items():
        cov, tot = m.get("covered"), m.get("total")
        if (cov is None) != (tot is None) or (cov is not None and not 0 <= cov <= tot):
            problems.append(f"coverage.{name}: invalid counts {cov}/{tot}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tester", required=True, help="tester base URL (no /test suffix)")
    ap.add_argument("--target", required=True, help="system base URL (no /test suffix)")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--strict", action="store_true", help="exit 2 unless every test passed or was skipped")
    args = ap.parse_args()
    tester = args.tester.rstrip("/")

    with httpx.Client(timeout=args.timeout) as c:
        r = c.post(f"{tester}/test/setup", json={"target_url": args.target})
        print(f"setup -> {r.status_code} {r.text[:300]}")
        if r.status_code != 201:
            return 1
        sid = r.json()["session_id"]
        try:
            run = c.post(f"{tester}/test/run", json={"session_id": sid})
            print(f"run -> {run.status_code}")
            report = run.json() if run.status_code == 200 else None
        except httpx.HTTPError as exc:
            print(f"run request failed ({type(exc).__name__}); fetching stored report")
            report = None
        if report is None:
            rep = c.get(f"{tester}/test/report", params={"session_id": sid})
            print(f"report -> {rep.status_code}")
            if rep.status_code != 200:
                return 1
            report = rep.json()

    out = ROOT / "reports" / "cross-team"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{sid[:8]}.json"
    path.write_text(json.dumps(report, indent=2))

    counts: dict[str, int] = {}
    for res in report.get("results", []):
        counts[res["outcome"]] = counts.get(res["outcome"], 0) + 1
    print(f"session {sid}  target {report.get('target_url')}  results {counts}")
    for name, m in report.get("coverage", {}).items():
        print(f"  coverage.{name}: {m.get('covered')}/{m.get('total')}")
    for res in report.get("results", []):
        if res["outcome"] in ("fail", "error"):
            print(f"  {res['outcome']:5} {res.get('source', ''):13} {res['test_id']}: {res['message'][:140]}")
    problems = check_report(report)
    for p in problems:
        print(f"  INTERFACE PROBLEM: {p}")
    print(f"saved {path.relative_to(ROOT)}")
    if problems:
        return 1
    if args.strict and (counts.get("fail") or counts.get("error")):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
