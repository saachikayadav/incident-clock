"""AC-16 persistence check: data survives a service restart (REQ-15).

Restarting a service is outside what an HTTP test can do, so this is a script
with two ways to restart:

  # local / CI: the script runs the restart command itself
  python scripts/persistence_check.py --restart-cmd "./scripts/restart_local.sh"

  # deployed (e.g. Render): seed, restart from the dashboard, then verify
  python scripts/persistence_check.py --phase seed
  python scripts/persistence_check.py --phase verify

Environment: BASE_URL, API_KEY. Writes reports/persistence.json.
Exit code 0 = pass, 1 = fail.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

N = 100
STATE = Path("reports/persistence_state.json")
REPORT = Path("reports/persistence.json")


def client() -> httpx.Client:
    base = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    key = os.environ.get("API_KEY", "")
    if not key:
        sys.exit("API_KEY is required")
    return httpx.Client(base_url=base, headers={"X-API-Key": key}, timeout=60)


def seed(c: httpx.Client) -> dict[str, str]:
    assert c.post("/reset").status_code == 200
    created: dict[str, str] = {}
    for i in range(N):
        title = f"Persistence probe {i:03d}"
        r = c.post(
            "/incidents",
            json={
                "title": title,
                "description": "AC-16 persistence probe",
                "discoveredAt": "2025-09-22T14:30:00-04:00",
                "reporterName": "Persistence check",
            },
        )
        r.raise_for_status()
        created[r.json()["incidentId"]] = title
    first = next(iter(created))
    c.post(
        f"/incidents/{first}/evidence",
        json={"category": "TECHNICAL", "summary": "probe", "source": "probe", "collectedAt": "2025-09-22T15:00:00Z"},
    ).raise_for_status()
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"created": created, "evidenceOn": first}))
    print(f"seeded {len(created)} incidents (+1 evidence on {first})")
    return created


def wait_healthy(c: httpx.Client, timeout_s: float = 180) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if c.get("/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    sys.exit("service did not become healthy after restart")


def verify(c: httpx.Client) -> bool:
    state = json.loads(STATE.read_text())
    created: dict[str, str] = state["created"]
    missing, wrong = [], []
    for incident_id, title in created.items():
        r = c.get(f"/incidents/{incident_id}")
        if r.status_code != 200:
            missing.append(incident_id)
        elif r.json()["title"] != title:
            wrong.append(incident_id)
    ev = c.get(f"/incidents/{state['evidenceOn']}").json().get("evidence", [])
    ok = not missing and not wrong and len(ev) == 1
    result = {
        "checkedAt": datetime.now(UTC).isoformat(),
        "target": str(c.base_url),
        "serviceVersion": c.get("/health").headers.get("X-Service-Version"),
        "incidentsExpected": len(created),
        "incidentsFound": len(created) - len(missing),
        "titleMismatches": len(wrong),
        "evidenceSurvived": len(ev) == 1,
        "pass": ok,
    }
    REPORT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["seed", "verify", "all"], default="all")
    ap.add_argument("--restart-cmd", help="shell command that restarts the service (phase=all)")
    args = ap.parse_args()
    with client() as c:
        if args.phase == "seed":
            seed(c)
            return
        if args.phase == "verify":
            wait_healthy(c)
            sys.exit(0 if verify(c) else 1)
        if not args.restart_cmd:
            sys.exit("--restart-cmd is required with --phase all")
        seed(c)
        print(f"restarting: {args.restart_cmd}")
        subprocess.run(args.restart_cmd, shell=True, check=True)  # noqa: S602 - operator-supplied command
        wait_healthy(c)
        sys.exit(0 if verify(c) else 1)


if __name__ == "__main__":
    main()
