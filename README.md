# IncidentClock

Tracks SEC Form 8-K Item 1.05 cybersecurity incidents: incident records, supporting evidence,
human materiality decisions, and the four-business-day filing deadline. Course project
(Model-Based Agentic Software Engineering), implementing the pod's common interface
**contract v1.0** (`openapi/contract.yaml`).

**Current increment: Phase 5** — corrections (a new decision supersedes the current one, which
stays in the history, and status and deadline follow the correction) and the incident timeline
with evidence summary. Every operation of contract v1.0 is now implemented. Earlier increments:
Phase 4 decisions, REQ-08 state rules, the four-business-day deadline calculator (Eastern Time,
federal holidays), deadline status with `as_of` and filing timeliness; Phase 3 incidents,
evidence and the course cross-team testing interface (tester service + system `/test/setup` /
`/test/report`).

Deployed services (see `render.yaml`):

| Service | Base URL | Description |
|---|---|---|
| System | `https://incident-clock.onrender.com` (interactive docs at `/docs`) | Pod contract v1.0 (`openapi/contract.yaml`) + `/test/setup`, `/test/report` (`openapi/system-test-interface.yaml`) |
| Tester | `https://incident-clock-tester.onrender.com` | `/test/setup`, `/test/run`, `/test/report` (`openapi/tester.yaml`) |
| Web frontend | `https://incident-clock-frontend.onrender.com` | Browser UI for incidents and evidence (`frontend/`); not part of the pod contract |

## Status by requirement

| REQ | Capability | Status (Phase 5) | Evidence (tests) |
|---|---|---|---|
| REQ-01 | Create incident | complete | AC-01 `test_ac01_*` |
| REQ-02 | Reject invalid incident | complete¹ | AC-02 `test_ac02_*` |
| REQ-03 | Add evidence | complete | AC-04, AC-05 |
| REQ-04 | Record human decision | complete | AC-06, AC-07 |
| REQ-05 | Reject invalid decision | complete | AC-06 `test_ac06_*` |
| REQ-06 | Corrections | complete² | AC-08 `test_ac08_*`, `test_req06_*` |
| REQ-07 | No edits/deletes (405) | complete for every resource; superseded decisions kept (AC-08 history step: ISSUE-05/10) | `test_req07_*`, `test_ac08_*` |
| REQ-08 | State rules (409) | complete, including correction while FILED | AC-15 `test_ac15_*`, `test_req08_*` |
| REQ-09 | Deadline calculation | complete | AC-09, AC-10, `unit_tests/` |
| REQ-10 | Deadline status | complete | AC-07, AC-11 `test_ac11_*deadline_status*` |
| REQ-11 | Record filing, timeliness | complete (delivered early, needed for AC-15) | AC-11 |
| REQ-13 | API-key auth, HTTPS | complete (deployed over HTTPS on Render) | AC-14 `test_ac14_*` |
| REQ-12 | Timeline, evidence summary | complete² | AC-12, AC-13 `test_ac12_*`, `test_ac13_*`, `test_req12_*` |
| REQ-14 | Error format, reset, RFC 3339/UTC | complete for every operation | AC-01..07, AC-09..11, AC-15, AC-16, `test_req06_*`, `test_req12_*` |
| REQ-15 | Persistence, latency | complete locally; deployed latency passed, deployed restart check pending | AC-16, `scripts/persistence_check.py` |

¹ "Incident count unchanged" in AC-02 is not testable through contract v1.0 (docs/spec-issues.md ISSUE-01).
² Interim interpretations: a correction naming a superseded decision is 409 (ISSUE-24);
`discoveryToDeterminationDays` counts Eastern Time calendar days to the current decision (ISSUE-25;
AC-13 fixes whole calendar days). AC-08's history step is checked through the timeline (ISSUE-10).

## Operations

| Operation | Status |
|---|---|
| `GET /health` | implemented (no key) |
| `POST /incidents` | implemented |
| `GET /incidents/{incidentId}` | implemented (`currentDecision`, `filing`) |
| `POST /incidents/{incidentId}/decisions` | implemented (Phase 4) |
| `GET /incidents/{incidentId}/deadline-status` | implemented (Phase 4), optional `as_of` |
| `POST /incidents/{incidentId}/filing` | implemented (Phase 4) |
| `POST /incidents/{incidentId}/evidence` | implemented |
| `POST /reset` | implemented |
| `POST /incidents/{incidentId}/corrections` | implemented (Phase 5) |
| `GET /incidents/{incidentId}/timeline` | implemented (Phase 5) |
| `GET /openapi.yaml` | serves the contract file verbatim (not part of the contract) |
| `GET /docs` | interactive API docs (Swagger UI): click **Authorize**, paste the key, then **Try it out**. Public page; every API call from it still needs the key |
| `GET /openapi/system-test-interface.yaml` | the `/test/*` API description, used by `/docs` |
| `POST /test/setup`, `GET /test/report` | course testing interface (key required): clears project data, starts per-session line coverage, reports it |

Regenerate this table from live probes: `python scripts/operation_status.py`.

## Architecture

FastAPI (Python 3.12) → explicit validation (`app/validation.py`) → deadline module
(`app/deadline.py`) → `Store` (psycopg 3 pool) → PostgreSQL 16. Tables are append-only, enforced
by database triggers; status is derived, not stored; a decision's deadline is computed once and
stored with it. Holiday list: `fixtures/holidays.json` (federal holidays 2023–2027, ISSUE-17).
Models: `docs/models.md` (rendered PNGs in `docs/diagrams/`).

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export API_KEY=test-key DATABASE_URL=postgresql://postgres@localhost:5432/incidentclock BASE_URL=http://localhost:8000
scripts/serve_local.sh start            # uvicorn on :8000, logs in reports/service.log
scripts/serve_local.sh stop             # when you're done
```

If startup fails with `role "postgres" does not exist` (common with Homebrew Postgres,
which only creates a role for your macOS user), either create the role once with
`createuser -s postgres` or connect as yourself:
`DATABASE_URL=postgresql://localhost:5432/incidentclock`.

### Web frontend (Flask)

A server-rendered UI in `frontend/`: create an incident, find one by ID, view it with its
evidence, and add evidence. Phase 4 operations (decisions, deadline status, filing) are
not in the UI yet; use the API or `/docs` for them. The Flask app calls the API with the
key, so the key never reaches the browser and the API needs no CORS.

**Prerequisite:** the API must be running (steps above, or a deployed URL).

```bash
# one-time: frontend dependencies (Flask, httpx, tzdata), in the same .venv
pip install -r frontend/requirements.txt

# each new terminal: activate the venv and set the variables
. .venv/bin/activate
export INCIDENT_API_URL=http://localhost:8000 API_KEY=test-key
python frontend/app.py                  # http://127.0.0.1:5001, Ctrl+C to stop
```

The backend runs in the background, so one terminal is enough: start the API with
`scripts/serve_local.sh start`, then run the frontend in the foreground.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `API_KEY` | yes | - | The API's key (same value the API was started with); sent as `X-API-Key` |
| `INCIDENT_API_URL` | no | `http://127.0.0.1:8000` | API base URL; must be `https://` unless it is localhost (REQ-13) |
| `FLASK_SECRET_KEY` | no | random per start | Signs the session cookie; without it, "Recent incidents" clears on restart |
| `FRONTEND_PORT` | no | `5001` | Port for the frontend (5000 is taken by AirPlay on macOS) |

Notes:

- `python frontend/app.py` starts Flask's development server with debug on. It is for
  local use only. Render runs it with gunicorn instead (see `render.yaml`).
- The deployed frontend has no login: anyone with its URL can create incidents through it.
- Times are entered as local time plus an explicit UTC offset (the API refuses timestamps
  without one) and shown in UTC with Eastern Time in parentheses.
- The API has no list operation, so "Recent incidents" holds only the incidents this
  browser created or opened. It lives in a browser cookie, so after `POST /reset` it can
  still list IDs that no longer exist.
- If the page shows **API unreachable**, check that the API is running and that
  `INCIDENT_API_URL` and `API_KEY` match it.

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
and the deadline unit tests (`pytest unit_tests`) — all run in CI (`.github/workflows/ci.yml`) before the contract tests. CI then starts the system,
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

## Verified results (2026-10-18 EDT, tester `b87ac9e`)

| Run | Result | Coverage (code / component / system) |
|---|---|---|
| Our tester → our system | 81 pass, 0 fail, 1 skip | 344/420, 5/10, 8/16 |
| Our tester → podmate system | 81 pass, 0 fail, 1 skip | 140/522, 5/10, 8/16 |
| Podmate tester → our system | 48/48 pass (their report) | 325/406, n/a, 8/16 |

## Known limitations

- Interim Phase 5 interpretations (ISSUE-24…26): 409 for a correction naming a superseded decision;
  `discoveryToDeterminationDays` in Eastern Time calendar days to the current decision; no ordering
  rule on a correction's `determinedAt`, so a correction can move a passed deadline.
- No operation returns a superseded decision's fields; the history shows only event references
  (ISSUE-10).
- Deadlines are supported for determinations 2023-01-01..2027-12-20 (holiday list range, ISSUE-17).
- Free plan: 15-minute idle spin-down (~60 s cold start). The free database expires 30 days after
  creation; it expired 2026-11-17, was recreated empty on 2026-11-19, and expires again around 2026-12-19.
- The web frontend has no decision, correction, deadline, filing or timeline screens, and no login
  (anyone with its URL can create incidents).
- One test session per system; concurrent runs reset each other's data (docs/spec-issues.md ISSUE-12).
- AC-02's "count unchanged" check cannot run: contract v1.0 has no list operation (ISSUE-01).

Full list: docs/spec-issues.md, `docs/phase3-report.md` and `docs/phase4-report.md` (Q7.2).
