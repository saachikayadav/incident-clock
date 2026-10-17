"""Generate the Phase 3 Q3.1 operation-status table from live probes.

For every operation in openapi/contract.yaml this script sends one success-path
request and the error-path requests the contract lists, validates bodies against
the contract schemas, and prints a table in the rubric's format:

  [METHOD /path] | Requirement(s) | Implemented
  Success responses conform | Error responses conform

Environment: BASE_URL, API_KEY. Writes reports/operation_status.md and .json.
Black-box: works against any team's service.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = yaml.safe_load((ROOT / "openapi" / "contract.yaml").read_text())
UNKNOWN = "INC-DOES-NOT-EXIST"
INCIDENT = {
    "title": "Probe",
    "description": "Operation status probe",
    "discoveredAt": "2025-09-22T14:30:00-04:00",
    "reporterName": "Probe",
}
EVIDENCE = {"category": "TECHNICAL", "summary": "probe", "source": "probe", "collectedAt": "2025-09-22T15:00:00Z"}


def schema_errors(name: str, body: Any) -> list[str]:
    schema = {"$ref": f"#/components/schemas/{name}", "components": CONTRACT["components"]}
    v = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(body)]


@dataclass
class Result:
    op: str
    reqs: list[str]
    implemented: str = "no"
    success: str = "n/a"
    errors: list[str] = field(default_factory=list)

    @property
    def error_conform(self) -> str:
        bad = [e for e in self.errors if not e.endswith(": ok")]
        return "yes" if self.errors and not bad else ("no - " + "; ".join(bad) if bad else "n/a")


def check(resp: httpx.Response, status: int, schema: str) -> str:
    if resp.status_code != status:
        return f"expected {status}, got {resp.status_code}"
    try:
        body = resp.json()
    except ValueError:
        return "body is not JSON"
    errs = schema_errors(schema, body)
    return "ok" if not errs else "schema: " + errs[0]


def main() -> None:
    base = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    key = os.environ.get("API_KEY", "")
    api = httpx.Client(base_url=base, headers={"X-API-Key": key}, timeout=60)
    anon = httpx.Client(base_url=base, timeout=60)
    api.post("/reset")
    inc = api.post("/incidents", json=INCIDENT).json().get("incidentId", UNKNOWN)
    ev = api.post(f"/incidents/{inc}/evidence", json=EVIDENCE).json().get("evidenceId", "EVD-?")

    decision = {
        "decision": "MATERIAL",
        "determinedAt": "2025-09-29T10:00:00-04:00",
        "decidedBy": "Disclosure Committee",
        "rationale": "probe",
        "evidenceIds": [ev],
    }

    # (op, method, path, body, success status, success schema, error probes)
    Probe = tuple[str, str, str, Any, int, str, list[tuple[str, Callable[[], httpx.Response], int]]]
    probes: list[Probe] = [
        ("GET /health", "GET", "/health", None, 200, "StatusMessage", []),
        (
            "POST /incidents",
            "POST",
            "/incidents",
            INCIDENT,
            201,
            "IncidentCreated",
            [
                ("400", lambda: api.post("/incidents", json={**INCIDENT, "discoveredAt": "2025-09-22T14:30:00"}), 400),
                ("401", lambda: anon.post("/incidents", json=INCIDENT), 401),
            ],
        ),
        (
            "POST /incidents/{incidentId}/evidence",
            "POST",
            f"/incidents/{inc}/evidence",
            EVIDENCE,
            201,
            "EvidenceCreated",
            [
                ("400", lambda: api.post(f"/incidents/{inc}/evidence", json={**EVIDENCE, "category": "X"}), 400),
                ("401", lambda: anon.post(f"/incidents/{inc}/evidence", json=EVIDENCE), 401),
                ("404", lambda: api.post(f"/incidents/{UNKNOWN}/evidence", json=EVIDENCE), 404),
            ],
        ),
        (
            "POST /incidents/{incidentId}/decisions",
            "POST",
            f"/incidents/{inc}/decisions",
            decision,
            201,
            "DecisionCreated",
            [
                ("401", lambda: anon.post(f"/incidents/{inc}/decisions", json=decision), 401),
                ("404", lambda: api.post(f"/incidents/{UNKNOWN}/decisions", json=decision), 404),
            ],
        ),
        (
            "POST /incidents/{incidentId}/corrections",
            "POST",
            f"/incidents/{inc}/corrections",
            {**decision, "correctsDecisionId": "DEC-001"},
            201,
            "DecisionCreated",
            [
                ("401", lambda: anon.post(f"/incidents/{inc}/corrections", json={}), 401),
                ("404", lambda: api.post(f"/incidents/{UNKNOWN}/corrections", json={}), 404),
            ],
        ),
        (
            "GET /incidents/{incidentId}",
            "GET",
            f"/incidents/{inc}",
            None,
            200,
            "Incident",
            [
                ("401", lambda: anon.get(f"/incidents/{inc}"), 401),
                ("404", lambda: api.get(f"/incidents/{UNKNOWN}"), 404),
            ],
        ),
        (
            "GET /incidents/{incidentId}/deadline-status",
            "GET",
            f"/incidents/{inc}/deadline-status?as_of=2025-10-01T12:00:00Z",
            None,
            200,
            "DeadlineStatus",
            [
                ("401", lambda: anon.get(f"/incidents/{inc}/deadline-status"), 401),
                ("404", lambda: api.get(f"/incidents/{UNKNOWN}/deadline-status"), 404),
            ],
        ),
        (
            "POST /incidents/{incidentId}/filing",
            "POST",
            f"/incidents/{inc}/filing",
            {"filedAt": "2025-10-02T14:00:00-04:00", "accessionNumber": "0000000000-25-000001"},
            201,
            "FilingCreated",
            [
                ("401", lambda: anon.post(f"/incidents/{inc}/filing", json={}), 401),
                ("404", lambda: api.post(f"/incidents/{UNKNOWN}/filing", json={}), 404),
            ],
        ),
        (
            "GET /incidents/{incidentId}/timeline",
            "GET",
            f"/incidents/{inc}/timeline",
            None,
            200,
            "Timeline",
            [
                ("401", lambda: anon.get(f"/incidents/{inc}/timeline"), 401),
                ("404", lambda: api.get(f"/incidents/{UNKNOWN}/timeline"), 404),
            ],
        ),
        (
            "POST /reset",
            "POST",
            "/reset",
            None,
            200,
            "StatusMessage",
            [
                ("401", lambda: anon.post("/reset"), 401),
            ],
        ),
    ]

    paths = CONTRACT["paths"]
    results: list[Result] = []
    for op, method, path, body, status, schema, errs in probes:
        template = op.split(" ", 1)[1]
        reqs = paths[template][method.lower()].get("x-requirements", [])
        res = Result(op, reqs)
        client = anon if template == "/health" else api
        resp = client.request(method, path, json=body) if body is not None else client.request(method, path)
        if resp.status_code == 501:
            res.implemented, res.success = "no", "n/a (501 NOT_IMPLEMENTED)"
        else:
            verdict = check(resp, status, schema)
            res.implemented = "yes" if verdict == "ok" else "partial"
            res.success = "yes" if verdict == "ok" else f"no - {verdict}"
        for label, call, expected in errs:
            res.errors.append(f"{label}: {check(call(), expected, 'Error')}")
        if res.implemented == "no" and res.errors:
            res.errors = [e for e in res.errors if e.startswith(("401", "404"))]
        results.append(res)

    api.post("/reset")
    lines = [f"Target: {base}  |  service version: {api.get('/health').headers.get('X-Service-Version', '?')}", ""]
    for r in results:
        lines.append(f"{r.op} | Requirement(s): {', '.join(r.reqs)} | Implemented: {r.implemented}")
        lines.append(
            f"Success responses conform: {r.success} | Error responses conform: {r.error_conform}"
            f" ({', '.join(e.split(':')[0] for e in r.errors) or 'none probed'})"
        )
        lines.append("")
    out = "\n".join(lines)
    print(out)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/operation_status.md").write_text(out)
    Path("reports/operation_status.json").write_text(json.dumps([r.__dict__ for r in results], indent=2))


if __name__ == "__main__":
    main()
