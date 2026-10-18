# IncidentClock

Tracks SEC Form 8-K Item 1.05 cybersecurity incidents: incident records, supporting evidence,
human materiality decisions, and the four-business-day filing deadline. Course project
(Model-Based Agentic Software Engineering), implementing the pod's common interface
**contract v1.0** (`openapi/contract.yaml`).

**Current increment: Phase 3** — incident and evidence management behind the authenticated
common API, plus the course cross-team testing interface: a deployed **tester** service and the
system's `/test/setup` / `/test/report` endpoints. Decisions, deadlines, filings, and timelines
arrive in Phases 4–5.

Two deployed services (see `render.yaml`):

| Service | Base URL | Description |
|---|---|---|
| System | `https://<system>.onrender.com` | Pod contract v1.0 (`openapi/contract.yaml`) + `/test/setup`, `/test/report` (`openapi/system-test-interface.yaml`) |
| Tester | `https://<tester>.onrender.com` | `/test/setup`, `/test/run`, `/test/report` (`openapi/tester.yaml`) |

## Status by requirement

| REQ | Capability | Phase 3 status | Evidence (tests) |
|---|---|---|---|
| REQ-01 | Create incident | complete | AC-01 `test_ac01_*` |
| REQ-02 | Reject invalid incident | complete¹ | AC-02 `test_ac02_*` |
| REQ-03 | Add evidence | complete | AC-04, AC-05 |
| REQ-07 | No edits/deletes (405) | partial — incidents only; other resources arrive P4–5 | `test_req07_*` |
| REQ-13 | API-key auth, HTTPS | complete in code; HTTPS pending deploy | AC-14 `test_ac14_*` |
| REQ-14 | Error format, reset, RFC 3339/UTC | partial — for delivered ops | AC-01..05, AC-16 |
| REQ-15 | Persistence, latency | complete locally; deployed run pending | AC-16, `scripts/persistence_check.py` |
| REQ-04–06, 08–12 | Decisions, deadlines, filing, timeline | not started (P4–5); routes return 501 | — |

¹ "Incident count unchanged" in AC-02 is not testable through contract v1.0 (docs/spec-issues.md ISSUE-01).

## Operations

| Operation | Status |
|---|---|
| `GET /health` | implemented (no key) |
| `POST /incidents` | implemented |
| `GET /incidents/{incidentId}` | implemented (`currentDecision`, `filing` always `null` until P4–5) |
| `POST /incidents/{incidentId}/evidence` | implemented |
| `POST /reset` | implemented |
| `POST .../decisions`, `POST .../corrections`, `GET .../deadline-status`, `POST .../filing`, `GET .../timeline` | 401/404 enforced, otherwise `501 NOT_IMPLEMENTED` |
| `GET /openapi.yaml` | serves the contract file verbatim (not part of the contract) |
| `GET /docs` | interactive API docs (Swagger UI): click **Authorize**, paste the key, then **Try it out**. Public page; every API call from it still needs the key |
| `GET /openapi/system-test-interface.yaml` | the `/test/*` API description, used by `/docs` |
| `POST /test/setup`, `GET /test/report` | course testing interface (key required): clears project data, starts per-session line coverage, reports it |

Regenerate this table from live probes: `python scripts/operation_status.py`.

## Architecture

FastAPI (Python 3.12) → explicit validation (`app/validation.py`) → `Store` (psycopg 3 pool) →
PostgreSQL 16. Tables are append-only, enforced by database triggers; status is derived, not stored.
Models: `docs/models.md` (rendered PNGs in `docs/diagrams/`).

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export API_KEY=test-key DATABASE_URL=postgresql://postgres@localhost:5432/incidentclock BASE_URL=http://localhost:8000
scripts/serve_local.sh start            # uvicorn on :8000, logs in reports/service.log
```

## Test any team's service (no code changes)

```bash
BASE_URL=https://<team-service> API_KEY=<shared key> python -m pytest      # contract suite
BASE_URL=... API_KEY=... python scripts/operation_status.py                # Q3.1 table
python scripts/persistence_check.py --restart-cmd "scripts/serve_local.sh restart"   # local restart
python scripts/persistence_check.py --phase seed   # deployed: seed, restart in dashboard, then --phase verify
```

Every test starts with `POST /reset`. **Do not run the suite against a service whose data you need.**
Tests marked `provisional` check behavior the pod has not fixed yet (docs/spec-issues.md); run
`pytest -m "not provisional"` for contract-only results. JUnit XML is written to `reports/junit.xml`.

## Course cross-team testing interface

**Tester** (`tester/`): `POST /test/setup {"target_url"}` prepares the target through its
`/test/setup` and returns a session ID; `POST /test/run {"session_id"}` runs the test plan once
and returns the suite report; `GET /test/report?session_id=` returns the stored report (409
until the suite ends). The test plan *is* the contract suite in `tests/`, run in a subprocess
with `-m "not provisional"`, so CI, local runs and cross-team runs share the same oracles.

- Outcomes: `pass`; `fail` (answer differs from the contract); `error` with `source`
  `system` (unexpected 5xx or failed precondition), `communication` (timeout / unreachable),
  `tester` (abort), `unknown`; `skip` (with reason).
- Coverage: `code` comes from the target's `/test/report`; `component` = contract operations
  actually reached (ISSUE-11); `system` = AC-01..AC-16 with at least one evaluated test.
- Access: the tester sends a key only to targets in its `TARGETS` setting
  (`{"https://system-base": "key"}`); any other `target_url` gets 400.
- Sessions and reports are in memory: a restart or free-plan spin-down clears them.

**System** (`app/main.py`, `app/coverage_session.py`): `/test/setup` clears project data,
registers the session (IDs are never reusable: 409) and restarts line coverage of `app/`
(coverage.py `sysmon` core, so worker threads are traced). `/test/report` returns
`coverage.code`. One session is active; a new setup supersedes it (ISSUE-12).

Run a cross-team check exactly as graders do, and keep the report:

```bash
python scripts/cross_team_run.py --tester https://<tester> --target https://<system>
```

Registry notes (maximum times, free plan, including a cold start of about a minute):
tester setup 150 s, tester run 600 s, system setup 90 s.

## Static checks

`ruff check . && ruff format --check . && mypy && openapi-spec-validator openapi/*.yaml`,
`pip-audit` on both requirement sets, and the tester self-tests (`pytest tester_tests`) —
all run in CI (`.github/workflows/ci.yml`) before the contract tests. CI then starts the system,
runs the contract suite, the persistence check, the system `/test/*` checks, and a full
tester → system run through `scripts/cross_team_run.py --strict`.

## Deploy (Render)

`render.yaml` is a Blueprint: the system (Docker web service + Postgres 16) and the tester
(Docker web service, `Dockerfile.tester`), region `ohio`, free plan. `API_KEY` (system) and
`TARGETS` (tester) are entered once in the dashboard (`sync: false`); `DATABASE_URL` is wired
from the database. After the first deploy, set the tester's `TARGETS` to include our own system
URL and each podmate system URL with its key. `autoDeployTrigger: checksPass` deploys a commit only after GitHub checks pass.
The running commit is returned in the `X-Service-Version` header (from `RENDER_GIT_COMMIT`).

Free-plan constraints that podmates and graders should expect:
- the service spins down after 15 minutes idle; the first request then takes about a minute;
- the free Postgres database expires 30 days after creation (1 GB, no backups).

## Observability

One JSON line per request on stdout (Render log stream): `request_id`, `method`, `path`,
`status`, `latency_ms`, `error_code`, `version`. Plus `startup`, `reset`, and `unhandled_exception`
events. Bodies and `X-API-Key` are never logged. Every response carries `X-Request-ID`.

## Known limitations

See docs/spec-issues.md and the Phase 3 report draft (`docs/phase3-report.md`).
