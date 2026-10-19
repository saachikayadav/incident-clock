# Project Phase 3 — draft answers

Evidence base: local runs on 2026-10-17 05:09 UTC and 2026-10-18 20:10 UTC against PostgreSQL 16,
and the deployed services at commit `63cf444` (grader sequence run 2026-10-18 22:44 UTC; CI run
https://github.com/saachikayadav/incident-clock/actions/runs/39172088813). Items marked **[NEEDS VERIFICATION]** depend on the
deployment, CI, or pod actions that have not happened yet; **[REQUIRES TEAM INPUT]** needs facts
only the team has. Replace every marker before submitting.

---

## Q1 Delivered Increment

### Q1.1 Increment description

Delivered capability: Through the pod's authenticated common interface, a compliance or incident-response user can now record a cybersecurity incident with its discovery time, attach evidence in the four contract categories, and retrieve the incident with all of its evidence. Every record is persisted in PostgreSQL and is append-only, enforced both by the API (405 on edits/deletes) and by database triggers. Invalid input is rejected with a 400 that names the offending field, and timestamps must carry a UTC offset. Unknown incidents return 404, and missing or wrong API keys return 401. The increment establishes the timestamped evidence trail that the Phase 4 materiality decision and four-business-day deadline will build on. Operations scheduled for Phases 4–5 are routed and authenticated but return 501 NOT_IMPLEMENTED. For cross-team testing we also deliver the course interface. A deployed tester service prepares any registered pod system, runs our contract suite against it, and returns a report with per-test outcomes and code, component and system coverage. The system exposes `/test/setup` and `/test/report`, which return per-session line coverage.

Users/stakeholders: incident-response and compliance staff at SEC registrants; disclosure committee (consumer of the evidence record); podmate team and graders (cross-team test clients).
Regulatory provision(s): Form 8-K Item 1.05(a) and Instruction 1 — nature, scope, timing and impact of the incident, and timing of the materiality determination relative to discovery [1]; 17 CFR 240.13a-15(e) disclosure controls (accurate, retained records) [2].

REQ-01 - Create incident │ Status: complete │ Demonstrated by: AC-01
REQ-02 - Invalid incident │ Status: complete │ Demonstrated by: AC-02
If partial: the AC-02 "incident count unchanged" check cannot run through contract v1.0, which has no list operation. It is skipped and logged as ISSUE-01; the behavior itself (nothing is inserted on a 400) is enforced in code by validating before the single INSERT transaction.
REQ-03 - Add evidence │ Status: complete │ Demonstrated by: AC-04, AC-05
REQ-07 - No edits or deletes │ Status: partial │ Demonstrated by: AC-08 (Phase 3 portion: `test_req07_*`)
If partial: covers incidents and evidence; decisions and filings do not exist until Phases 4–5. AC-08's decision-history steps are blocked by ISSUE-05/ISSUE-10.
REQ-13 - Authentication │ Status: complete │ Demonstrated by: AC-14
If partial: API-key enforcement is complete and tested. HTTPS verified on the deployed service: `test_ac14_served_over_https` passed in the deployed run (2026-10-18 22:44 UTC). Remaining manual part: code inspection.
REQ-14 - Errors, reset, formats │ Status: partial │ Demonstrated by: AC-01–AC-05, AC-16
If partial: complete for the Phase 3 operations; Phase 4–5 operations are not implemented yet.
REQ-15 - Persistence and performance │ Status: partial │ Demonstrated by: AC-16
If partial: verified locally (100/100 incidents survive restart; 100% of 200 requests under 1 s, p95 4 ms). Deployed: the AC-16 latency test passed against `https://incident-clock.onrender.com` (2026-10-18 22:44 UTC); a restart-persistence check on the deployed database is still to be run **[NEEDS VERIFICATION: `persistence_check.py --phase seed`, Manual Deploy → Restart, `--phase verify`]**.

### Q1.2 Comparison with the Phase 2 plan

Every capability in the Phase 2 §6.1 milestone was implemented: incident and evidence data models, persistent PostgreSQL storage, API-key authentication, `/health`, `POST /incidents`, `GET /incidents/{id}`, evidence, `/reset`, synthetic fixtures (`fixtures/phase3.json`), and automated tests for AC-01–AC-04. We also delivered AC-05, AC-14, the REQ-07 incident portion, and AC-16 persistence/latency checks, because REQ-03, REQ-13 and REQ-15 otherwise had no acceptance evidence. The deployable web service is live on Render (`https://incident-clock.onrender.com`, commit `63cf444`) and passed the full suite there through our deployed tester (81 pass, 1 skip). The pod's *shared* fixture repository was not created; our fixtures live in this repository **[REQUIRES TEAM INPUT: confirm with the podmate team]**. The course cross-team testing interface (tester service and system `/test/*` endpoints) is additional Phase 3 work required by the course, not by our §6.1 plan; it is delivered. No instructor-required scope changes occurred, and no shared scope was reduced.

---

## Q2 Deployment and Operation

### Q2.1 Deployed web service

Two services run on Render, both defined in `render.yaml` [3] and both Docker web services (Python 3.12 + uvicorn) in region Ohio on the free plan. The system uses a Render Postgres 16 database; the tester is stateless apart from in-memory reports. System: `https://incident-clock.onrender.com`; tester: `https://incident-clock-tester.onrender.com`; both Live on commit `63cf444`. Each system response carries an `X-Service-Version` header, and each tester report a `tester_version` field, holding the first 12 characters of `RENDER_GIT_COMMIT`, the commit SHA Render deploys [4]. That maps the running version to a commit: on 2026-10-18 the system returned `X-Service-Version: 63cf44491ece` and the tester reported `tester_version: 63cf44491ece`, matching `main`. A new version is released by merging to `main`. GitHub Actions runs static checks and the contract suite, and Render's `autoDeployTrigger: checksPass` deploys the commit only after those checks pass [3]. The service is not always on: free web services spin down after 15 idle minutes and take about a minute to wake on the next request [5]. The free database expires 30 days after creation (1 GB, no backups) [5] (database created 2026-10-18, so it expires 2026-11-17), and workspaces get 750 free instance hours per month [5]. Podmates should send one `GET /health` and allow up to 60 s before timing tests. They should also coordinate before running a suite: `/test/setup` and every test's `POST /reset` wipe all data, and only one session is active per system. The tester keeps sessions and reports in memory, so a spin-down after 15 idle minutes clears them; fetch reports promptly. The tester only tests targets registered in its `TARGETS` setting.

### Q2.2 Registry and team documentation

Registry entry: **[REQUIRES TEAM INPUT: class registry location]** │ Updated on: **[date]**. The entry should contain: System base URL `https://incident-clock.onrender.com`; Tester base URL `https://incident-clock-tester.onrender.com`; Intra-pod specification URL (the pod's shared spec, with `docs/spec-issues.md` ISSUE-11…16 for preparation, resets and coverage definitions); Access/run notes: "System endpoints need the pod test key in `X-API-Key`; ask the team, it is never in the sheet. Tester endpoints are open; podmate systems must be registered in our tester first. Max times (free plan, including a ~60 s cold start): tester setup 150 s, tester run 600 s, system setup 90 s. One run per target at a time."
Team documentation: `README.md`, `docs/models.md` (+ `docs/diagrams/*.png`), `docs/spec-issues.md`, `openapi/contract.yaml` in `github.com/saachikayadav/incident-clock` │ Updated on: **[date of push]**

### Q2.3 Operational experience supported by observability evidence

The Phase 2 plan (§7.3) held without change. Data persists in PostgreSQL, and status is derived at read time rather than stored. `POST /reset` runs `TRUNCATE … RESTART IDENTITY`, which clears all tables and restarts ID numbering; it bypasses the row-level triggers that otherwise reject any UPDATE or DELETE [6]. `API_KEY` is a Render secret entered once in the dashboard (`sync: false`), and `DATABASE_URL` is injected from the database [3]. Neither is in the repository, and `.env` is git-ignored. Failures are detected through one structured JSON log line per request (`request_id`, `method`, `path`, `status`, `latency_ms`, `error_code`, `version`). The logs also record `startup`, `reset`, and `unhandled_exception` events, and `/health` checks the database and returns 503 if it is unreachable. Request bodies and API keys are never logged. The tester logs one JSON line per setup, run start and run end, including the session ID, target and outcome summary. A local test run produced 1,594 request lines. Excerpt **[NEEDS VERIFICATION: replace with lines from the Render log stream after deploy]**:

```
{"ts": "2026-10-17T05:07:09.038Z", "level": "info", "event": "request", "request_id": "756dcce844fb4f51", "method": "POST", "path": "/incidents", "status": 201, "latency_ms": 4.8, "error_code": null, "version": "local-uncomm"}
{"ts": "2026-10-17T05:07:09.210Z", "level": "warning", "event": "request", "request_id": "4de41e3e85564f10", "method": "POST", "path": "/incidents", "status": 400, "latency_ms": 0.9, "error_code": "INVALID_DISCOVERED_AT", "version": "local-uncomm"}
{"ts": "2026-10-17T05:07:10.571Z", "level": "warning", "event": "request", "request_id": "4508825e60244bbf", "method": "POST", "path": "/incidents", "status": 401, "latency_ms": 0.0, "error_code": "UNAUTHORIZED", "version": "local-uncomm"}
```

---

## Q3 Implementation and Interface Conformance

### Q3.1 Operation status
(Generated by `scripts/operation_status.py` from live probes against the local service; re-run against the deployed URL before submitting.)

GET /health │ Requirement(s): REQ-13 │ Implemented: yes
Success responses conform: yes │ Error responses conform: n/a (contract lists none; returns 503 `{status}` if the DB is down)

POST /incidents │ Requirement(s): REQ-01, REQ-02 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400, 401)

POST /incidents/{incidentId}/evidence │ Requirement(s): REQ-03 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400, 401, 404)

POST /incidents/{incidentId}/decisions │ Requirement(s): REQ-04, REQ-05, REQ-08, REQ-09 │ Implemented: no (Phase 4)
Success responses conform: n/a (501) │ Error responses conform: 401, 404 yes; 400, 409 not yet

POST /incidents/{incidentId}/corrections │ Requirement(s): REQ-06, REQ-08, REQ-09 │ Implemented: no (Phase 5)
Success responses conform: n/a (501) │ Error responses conform: 401, 404 yes; 400, 409 not yet

GET /incidents/{incidentId} │ Requirement(s): REQ-01, REQ-03, REQ-04, REQ-06 │ Implemented: partial
Success responses conform: yes (schema-valid; `currentDecision` and `filing` are always `null` until Phases 4–5) │ Error responses conform: yes (401, 404)

GET /incidents/{incidentId}/deadline-status │ Requirement(s): REQ-09, REQ-10 │ Implemented: no (Phase 4)
Success responses conform: n/a (501) │ Error responses conform: 401, 404 yes; 400 not yet

POST /incidents/{incidentId}/filing │ Requirement(s): REQ-08, REQ-11 │ Implemented: no (Phase 5)
Success responses conform: n/a (501) │ Error responses conform: 401, 404 yes; 400, 409 not yet

GET /incidents/{incidentId}/timeline │ Requirement(s): REQ-12 │ Implemented: no (Phase 5)
Success responses conform: n/a (501) │ Error responses conform: yes (401, 404)

POST /reset │ Requirement(s): REQ-14 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (401)

Course testing interface (not part of the pod contract; specified in `openapi/system-test-interface.yaml`, checked by `tester_tests/test_system_interface.py`):
POST /test/setup │ Implemented: yes │ Success responses conform: yes (201, same session_id) │ Error responses conform: yes (400, 401, 409 on reuse, 500 `source: system`)
GET /test/report │ Implemented: yes │ Success responses conform: yes (`coverage.code` with covered/total/basis) │ Error responses conform: yes (400, 401, 404)

Integration: This is the first increment, so every component is new. A request passes through one middleware, which assigns a request ID, enforces `X-API-Key` (401), times the request and writes the log line. It then reaches a route handler in `app/main.py`, which checks that the incident exists (404). Next, `app/validation.py` checks the body (400) instead of FastAPI's default 422 path [7]. Finally, `Store` (`app/db.py`, psycopg connection pool [8]) writes the record and its history event in one transaction. The `events` table is already populated, so the Phase 5 timeline will need no backfill, and Phase 4 adds a deadline module and a decisions table behind the same handlers. The `/test/*` routes reuse the same middleware and `Store` and add `coverage_session.py`. Setup clears project data and registers the session in the `test_sessions` table in one transaction, then restarts coverage measurement.

### Q3.2 Contract changes and pod communication

Contract version at delivery: v1.0 (unchanged; machine-readable transcription in `openapi/contract.yaml` [9]).
Changes since Phase 2: none.
Pod agreement: n/a — proposals ISSUE-01…ISSUE-10 in `docs/spec-issues.md` are to be raised with the pod **[REQUIRES TEAM INPUT: date and channel once raised]**.
Intentional deviations and resolution plan: (1) Operations not yet built return 501 `NOT_IMPLEMENTED` instead of a contract response (ISSUE-09), resolved as Phases 4–5 land. (2) `GET /openapi.yaml` is an extra, unauthenticated route serving the contract file; it is additive and does not change any contract operation. (3) Where the contract is silent we applied documented interim rules: max lengths (ISSUE-02), 404-before-400 order (ISSUE-03), `INVALID_<FIELD>` error codes (ISSUE-04), future `collectedAt` accepted (ISSUE-06), unknown fields ignored (ISSUE-07), and 503 on `/health` (ISSUE-08). We will adopt whatever the pod fixes in v1.1.

---

## Q4 Automated Validation

### Q4.1 Test runner and execution instructions

Base URL override: graders and podmates change the target only through the course interface. `POST <our tester>/test/setup {"target_url": "<any registered pod system base URL>"}` then `POST /test/run {"session_id"}`; no code changes. Outside the tester, the same suite runs with `BASE_URL=<system> API_KEY=<key> python -m pytest`, and `scripts/cross_team_run.py --tester … --target …` performs the grader sequence and saves the report. │ Response received: deployed, 2026-10-18 22:44 UTC: `POST https://incident-clock-tester.onrender.com/test/setup {"target_url": "https://incident-clock.onrender.com"}` → `201 {"session_id": "a1b154da-163b-40a9-8989-2ca1348efea9"}`; `POST /test/run` → `200` report in 30 s (82 results: 81 pass, 1 skip; coverage code 337/406, component 5/10, system 8/16); `GET /test/report` → `200`, byte-identical to the run response. Local, 2026-10-18: setup `201 {"session_id":"15bd0d6e-…"}`; run `200` with 82 results (80 pass, 2 skip), coverage code 332/406, component 5/10, system 8/16. │ Conforms to spec: yes. The report validates against `openapi/tester.yaml`, every planned test appears once with a unique ID and non-empty message, and every `error` carries a `source`. System `/test/*` and the pod contract validate against their OpenAPI files.
Known deviations from the OpenAPI spec: Phase 4–5 project operations return 501 (Q3.2). Tester reports carry four additional fields (`summary`, `started_at`, `duration_seconds`, `tester_version`). System `/test/*` error bodies carry an additional `error` code alongside `message` and `source`. No deviations in required fields or status codes.

### Q4.2 Tests for new functionality

AC-01 │ Requirement(s): REQ-01, REQ-14
Test(s): `test_ac01_create_returns_201_with_id_and_open_status`, `test_ac01_get_returns_identical_values`, `test_ac01_each_incident_gets_a_unique_id` │ Type: success │ Automated: yes
Test(s): `test_ac01_utc_offset_input_round_trips` (Z and +05:30 offsets normalized to UTC) │ Type: boundary │ Automated: yes

AC-02 │ Requirement(s): REQ-02, REQ-14
Test(s): `test_ac02_pod_fixture_cases_rejected` (the 3 AC cases), `test_ac02_missing_required_field` ×4, `test_ac02_empty_text_field` ×6, `test_ac02_null_field` ×4, `test_ac02_wrong_type` ×3, `test_ac02_malformed_discovered_at` ×7, `test_ac02_body_not_a_json_object` ×5 │ Type: failure │ Automated: yes
Test(s): `test_ac02_future_discovered_at_boundary`, `test_ac02_length_limit_boundary` ×2 (provisional, ISSUE-02) │ Type: boundary │ Automated: yes
Test(s): `test_ac02_rejected_request_creates_nothing` │ Type: failure │ Automated: no — skipped; the count check needs a list operation absent from v1.0 (ISSUE-01)

AC-03 │ Requirement(s): REQ-14
Test(s): `test_ac03_get_unknown_incident_404`, `test_ac03_post_evidence_unknown_incident_404`, `test_ac03_other_incident_operations_unknown_id_404` ×5, `test_ac03_reset_ids_do_not_resolve`, `test_ac03_unknown_incident_checked_before_body` (provisional, ISSUE-03) │ Type: failure │ Automated: yes

AC-04 │ Requirement(s): REQ-03
Test(s): `test_ac04_three_technical_items_linked_in_order`, `test_ac04_recorded_at_matches_create_response`, `test_ac04_evidence_not_leaked_across_incidents`, `test_ac04_all_categories_accepted` ×4 │ Type: success │ Automated: yes
Test(s): `test_ac04_invalid_evidence_rejected_and_not_stored` ×7, `test_ac04_missing_evidence_field_rejected` ×4 │ Type: failure │ Automated: yes

AC-05 │ Requirement(s): REQ-03
Test(s): `test_ac05_business_impact_stored_unchanged` │ Type: success │ Automated: yes

AC-08 (Phase 3 portion) │ Requirement(s): REQ-07
Test(s): `test_req07_incident_edit_or_delete_405` ×3 (PUT/PATCH/DELETE, record unchanged) │ Type: failure │ Automated: yes

AC-14 │ Requirement(s): REQ-13
Test(s): `test_ac14_valid_key_succeeds`, `test_ac14_health_needs_no_key` │ Type: success │ Automated: yes
Test(s): `test_ac14_missing_key_401` ×4, `test_ac14_wrong_key_401` ×4, `test_ac14_unauthorized_request_changes_nothing` │ Type: failure │ Automated: yes
Test(s): `test_ac14_served_over_https` │ Type: boundary │ Automated: yes against an https BASE_URL (skipped locally); code inspection part manual

AC-16 │ Requirement(s): REQ-14, REQ-15
Test(s): `test_ac16_reset_clears_all_records`, `test_ac16_latency_95pct_under_1s_with_100_incidents` │ Type: success / boundary │ Automated: yes
Test(s): `scripts/persistence_check.py` (100 incidents + evidence across a restart) │ Type: success │ Automated: yes locally/CI; deployed run needs a manual restart (`--phase seed` / `--phase verify`)

Course testing interface │ Requirement(s): REQ-14 (repeatable cross-team testing)
Test(s): `tester_tests/test_system_interface.py` (10: same-ID 201, data cleared, reuse 409 with nothing changed, coverage grows with requests, superseded session still reportable, 400/404/401 shapes) │ Type: success / failure │ Automated: yes (CI, against the running system)
Test(s): `tester_tests/test_service.py`, `tester_tests/test_reporting.py` (32: lifecycle, run-once 409, key never sent to unregistered targets, setup errors forwarded with status/message/source, communication errors, every planned test once, abort → `error/tester` then `skip`, coverage validation) │ Type: success / failure / boundary │ Automated: yes (CI)
Test(s): CI step "tester end-to-end": tester → system through `scripts/cross_team_run.py --strict` │ Type: success │ Automated: yes

Oracles: Every expected status, field and value comes from the Phase 2 acceptance criteria and §5.2 examples. Response bodies are validated against the contract schemas in `openapi/contract.yaml`, never against the implementation's own output, and timestamps are compared as parsed instants rather than strings. We trust the oracles because they can fail: three deliberately injected defects were each caught. Accepting offset-less timestamps failed 3 tests, returning FastAPI's default 422 failed 41, and validating the body before the 404 check failed 1. After each mutation the code was restored and verified byte-for-byte. We checked the tester's outcome classification the same way, against the real system with injected faults. A contract mismatch produced `fail` (39 tests). An internal error in the target produced `error/system` (21 tests). Stopping the target mid-suite produced `error/communication`, with code coverage null and the reason given. A 1.5 s run limit produced 500, with 77 stored results, one `error/tester` and 4 `skip`. Two mutations of the tester itself, removing the key guard and the run-once rule, each failed a self-test.

### Q4.3 Regression and static checks

CI run: https://github.com/saachikayadav/incident-clock/actions/runs/39172088813 (commit `63cf444`, success; first run on `366aec7`: https://github.com/saachikayadav/incident-clock/actions/runs/39009187556)

Every push and pull request re-runs the complete suite (all Phase 3 tests, and in later phases all earlier ones) against a fresh PostgreSQL 16 service container. Tests are added per phase and never removed, so Phase 3 behavior stays checked as Phases 4–5 change the same handlers. The persistence check, the operation-status probe, the system `/test/*` checks and a full tester → system run also execute on every build, and the JUnit and status reports are uploaded as artifacts. Render deploys only commits whose checks passed (`checksPass`), so a regression cannot reach the deployed service through the normal release path.

### Q4.4 Static checks

CI run: https://github.com/saachikayadav/incident-clock/actions/runs/39172088813

CI runs these checks on every push and PR: ruff lint (including security rules `S`), the ruff format check, mypy `--strict` over the system, tester, scripts and tests, `openapi-spec-validator` on all three API documents, `pip-audit` on both the system and tester dependencies, and the tester self-tests. They all run in a `static` job that the contract-test job depends on, so a failing static check stops testing, and through `checksPass` it also stops deployment. Blocking merges additionally requires enabling branch protection on `main` **[REQUIRES TEAM INPUT: enable "require status checks"]**. `pip-audit` has already paid off: it found 14 published advisories against the initial `starlette 0.46.2` pin, which we resolved by upgrading before the first deploy.

### Q4.5 Test results against the deployed system

Run date/time: 2026-10-18 22:44:22 UTC │ Version tested: `63cf444` (confirmed by `X-Service-Version` and `tester_version`)
Tests run: 82 │ Passed: 81 │ Failed: 0 │ Skipped: 1
How: our deployed tester against our deployed system, through the course interface (setup → run → report), i.e. exactly the grader sequence. Report validated: 82 unique test IDs, non-empty messages, valid outcomes, coverage counts within bounds; stored report identical to the run response.

Reference result, local service on the same code, 2026-10-17 05:09 UTC: 86 collected, 84 passed, 0 failed, 2 skipped. Contract-only (`-m "not provisional"`): 80 passed, 2 skipped. Expected deployed result: 85 passed, 1 skipped, because the HTTPS test runs once BASE_URL is https. Through the tester (non-provisional plan, 82 tests), local result 2026-10-18: 80 pass, 0 fail, 0 error, 2 skip; expected deployed: 81 pass, 1 skip.

Skipped: `test_ac02_rejected_request_creates_nothing` │ Classification: specification │ Cause: AC-02's count check needs a list operation absent from contract v1.0 (ISSUE-01) │ Plan: pod decides between adding `GET /incidents` and rewording AC-02 before Phase 4.
`test_ac14_served_over_https` (skipped in local runs because the target is http) ran and passed against the deployed HTTPS URL.

---

## Q5 Updated System Models

### Q5.1 Model updates

T1 Cross-team test session (sequence) │ Changed: new │ What changed and why: New model for the course testing interface. It shows grader → tester → system setup, the in-order test loop, coverage retrieval, the stored report, and the 400 branch for unregistered targets. │ Location: §T1, `t1-test-session.png`
A1 Architecture and data flow (component) │ Changed: yes │ What changed and why: Now includes the tester service (API, pytest subprocess, reporting), the system `/test/*` routes, `coverage_session.py` and the `test_sessions` table. Phase 2 §7.1 showed separate API, application/service and deadline-service layers. As built, the route handlers call validation and the Store directly, and the deadline module does not exist yet, so it is drawn dashed as "planned". We added Render, the log stream, and the CI → deploy path with commit-SHA traceability. │ Location: `docs/models.md` §A1, `docs/diagrams/a1-architecture.png`
M1 Incident status (state machine) │ Changed: yes (annotation) │ What changed and why: The states and transitions are unchanged. Transitions not yet implemented are labelled "planned P4/P5", and a note records that only OPEN is reachable in Phase 3. │ Location: §M1, `m1-incident-status.png`
M2 Information model (ER) │ Changed: yes │ What changed and why: Generated directly from `app/schema.sql`. It now shows the `events` history table (not in Phase 2), DB-generated IDs, the append-only triggers, and that no status column exists (status is derived). Decisions and filings tables are listed as planned. │ Location: §M2, `m2-information-model.png`
M3 Deadline calculation (activity) │ Changed: no │ What changed and why: not implemented yet; rule restated unchanged. │ Location: §M3
M4 Request check order (activity) │ Changed: yes │ What changed and why: It now shows the implemented order 401 → 405 → 404 → 400 → write, plus the 501 branch for Phase 4–5 operations and the per-request log line. │ Location: §M4, `m4-check-order.png`

**[REQUIRES TEAM INPUT: the Phase 2 model images were not available when these were drawn — compare against Screenshots 214411/214354/214024 and adjust the "what changed" text if the originals differ.]**

### Q5.2 Model-implementation consistency

Each model was derived from the code rather than from the plan. The ER model was written from `app/schema.sql`, M4 from the middleware and handler order in `app/main.py`, and A1 lists only modules that exist, with the planned deadline module drawn dashed. All diagrams are Mermaid source in the repository, rendered to PNG, so a model and the code it describes change in the same commit. The check-order model is also executable: `test_ac03_unknown_incident_checked_before_body` fails when the code's order departs from M4, and it did fail when we deliberately swapped the order. One divergence from Phase 2: the §7.1 sketch put an application/service layer between the API and persistence, but at Phase 3 size the handlers call validation and the Store directly. We corrected the model rather than add an empty layer to the code, and we will reintroduce a service layer in the model only when Phase 4's decision and deadline logic exists. **[REQUIRES TEAM INPUT: add who walked through the models, if a teammate did.]**

---

## Q6 Pod Cross-Team Readiness

### Q6.1 Cross-team test

Both directions ran on 2026-10-19 (UTC) through the deployed course interface: `POST /test/setup {target_url}` then `POST /test/run {session_id}` on a tester, so no code was changed to switch targets. Saved reports: `reports/cross-team/vs-podmates-1.json` (first run), `vs-podmates-2.json` (after the fix), `vs-ours.json`.

Our tests → **[team name]** service (`https://incident-api-356019173418.us-central1.run.app`) │ Date: 2026-10-19 02:45 UTC, tester `b87ac9e` │ Run/passed: 82 run, 81 passed, 0 failed, 0 errors, 1 skipped (AC-02 count check, ISSUE-01) │ Coverage: code 140/522, component 5/10, system 8/16 │ Main problem and owner: the first run (02:08 UTC, tester `63cf444`) reported 77 passed and 4 failed. All 4 failures were GET requests to which **our** tests attached an empty JSON body; their host (Google Cloud Run) rejects a GET with a body before the request reaches their service (HTML 400 over HTTP/1.1, stream reset over HTTP/2, confirmed with curl). Owner: us. We fixed the tests (commit `b87ac9e`, GenAI log C12) and the re-run had no failures.
**[team name]** tests → our service │ Date: 2026-10-19 **[REQUIRES TEAM INPUT: time]** │ Run/passed: **[REQUIRES TEAM INPUT: their numbers; they reported that it works]** │ Main problem and owner: our own self-test at about 02:38 UTC was reset by another client mid-run, most likely their suite **[NEEDS VERIFICATION: confirm with the podmates that they were testing us then]**. Each suite resets the system, so ours lost its data mid-run (78 passed, 2 failed, 1 error, all three caused by records vanishing). Owner: both teams (no coordination rule yet, ISSUE-12). Proposed rule: announce each run in the pod chat and never test the same system concurrently **[REQUIRES TEAM INPUT: pod agreement]**. Our self-test re-run at 02:44 UTC on tester `b87ac9e` gave 81 passed, 1 skipped (code 344/420, component 5/10, system 8/16).
Coverage per direction: copy `coverage.code`, `coverage.component` and `coverage.system` from each saved report. Code coverage comes from the target's own instrumentation (ours: line coverage of `app/` since setup), component coverage counts the contract operations reached (ISSUE-11), and system coverage counts AC-01…AC-16 with an evaluated test.

### Q6.2 Specification issues discovered

Issue: AC-02 and AC-16 (REQ-02, REQ-14, REQ-15) require counting incidents ("count unchanged", "all 100 remain", "no incidents remain after reset"), but contract v1.0 has no operation that lists or counts incidents.
Effect: The count half of AC-02 cannot be evaluated through the common interface by any team. Our suite skips it with a reason and verifies AC-16 through 404s on known IDs instead, and a podmate suite may count differently or not at all, so results are not comparable.
Pod decision or plan: **[REQUIRES TEAM INPUT: decision and date]**. We propose either adding `GET /incidents` (v1.1) or rewording both ACs to ID-based checks, decided before Phase 4 starts. Related gaps to bring to the same meeting: AC-08 targets "the old decision" and "decision history", but the contract has no URL for either (ISSUE-05/10), and max field lengths are still unset (ISSUE-02). The course testing interface adds items only the pod can fix: the component list for coverage (ISSUE-11), the session and concurrency model, given that contract v1.0 has no session field (ISSUE-12), and which tests form the shared plan (ISSUE-15).

---

## Q7 Status, Limitations and Next-Phase Adjustments

### Q7.1 What changed and what remains incomplete

Changed since Phase 2:
- Service built and tested: incident creation/retrieval and evidence (REQ-01, REQ-02, REQ-03; AC-01–AC-05).
- API-key auth and contract error format on every route (REQ-13, REQ-14; AC-03, AC-14).
- Append-only storage enforced by DB triggers; 405 on incident edits/deletes (REQ-07 partial; AC-08 partial).
- Persistence across restart and latency verified (REQ-15; AC-16), plus reset (REQ-14).
- CI with static checks, contract suite, persistence check, and Render `checksPass` deploy gating.
- Course cross-team testing interface: deployed tester service plus system `/test/setup` and `/test/report` with per-session code coverage (REQ-14; enables cross-team evaluation of all ACs).

Remaining incomplete:
- Materiality decisions, state rules, deadline calculation and status (REQ-04, 05, 08, 09, 10; AC-06, 07, 09, 10, 15) — Phase 4.
- Corrections, filings, timeline (REQ-06, 11, 12; AC-08, 11, 12, 13) — Phase 5.
- AC-02 count check and AC-08 history steps — blocked on ISSUE-01/05/10.
- Deployed-service verification of REQ-13 HTTPS and REQ-15 **[unless done before submission]**.

### Q7.2 Known limitations and defects

LIM-01 │ Free-plan cold start: the service sleeps after 15 min idle; first request takes ~1 min │ Affects: REQ-15, all operations │ Severity: medium
Workaround for podmates: `GET /health` and wait for 200 before timing; CI deployed job retries health │ Target phase: 6 (upgrade plan or keep-warm if graded)
LIM-02 │ Free Postgres expires 30 days after creation **[date]** │ Affects: REQ-15 │ Severity: high
Workaround for podmates: none needed; we must upgrade or recreate before expiry │ Target phase: 4
LIM-03 │ Decisions, corrections, deadline-status, filing, timeline return 501 │ Affects: REQ-04–06, 08–12 │ Severity: high (expected)
Workaround for podmates: run `-k "ac01 or ac02 or ac03 or ac04 or ac05 or ac14 or ac16"` │ Target phase: 4 / 5
LIM-04 │ `POST /reset` deletes everything for every caller holding the shared key │ Affects: REQ-14 │ Severity: medium
Workaround for podmates: announce runs in the pod channel; don't run concurrently with another team │ Target phase: 6
LIM-05 │ Interim interpretations where v1.0 is silent (lengths, check order, error codes, unknown fields, future `collectedAt`) │ Affects: REQ-02, REQ-03, REQ-14 │ Severity: low
Workaround for podmates: run `-m "not provisional"`; see `docs/spec-issues.md` │ Target phase: 4 (after pod v1.1)
LIM-06 │ Single shared API key, no rotation, no rate limiting │ Affects: REQ-13 │ Severity: low (synthetic data only)
Workaround for podmates: none │ Target phase: 6
LIM-07 │ `GET /incidents/{id}` returns all evidence with no pagination │ Affects: REQ-15 at large evidence counts │ Severity: low
Workaround for podmates: none needed at AC-16 scale │ Target phase: 6
LIM-09 │ Tester sessions and reports live in memory; a tester restart or free-plan spin-down (15 min idle) loses them │ Affects: course interface │ Severity: medium
Workaround for podmates: fetch `/test/report` right after a run; start a new session to repeat │ Target phase: 4 (persist reports if graders need longer retention)
LIM-10 │ One active session per system; overlapping runs against the same target interfere (setup and `POST /reset` clear all data) │ Affects: course interface, REQ-14 │ Severity: medium
Workaround for podmates: one run per target at a time; announce runs in the pod channel │ Target phase: pod decision (ISSUE-12)
LIM-11 │ Code coverage is line coverage only, and is lost if the system restarts mid-session (reported as null with that reason) │ Affects: coverage reporting │ Severity: low
Workaround for podmates: none │ Target phase: 6
LIM-08 │ ~~Docker images not yet built~~ **Resolved 2026-10-18**: both images (`Dockerfile`, `Dockerfile.tester`) built and deployed on Render at `63cf444` │ Affects: deployment │ Severity: —
Workaround for podmates: none needed │ Target phase: done (Phase 3)

### Q7.3 Adjustments to next phase milestone

The Phase 4 milestone (§6.2) holds unchanged in capability: decisions, state rules, the deadline calculator, and deadline status for REQ-04/05/08/09/10. Its tests depend on two pod decisions, though. AC-15 needs the 409 check to have a defined place in the check order (ISSUE-03), and the decision tests need the error-code catalogue (ISSUE-04), so both need pod agreement before Phase 4 tests are written. No sequencing change is needed: the `events` table and derived-status design already accommodate decisions.

Risk 1 (deadline arithmetic: Eastern Time, day-0 rule, holidays) remains open, because the calculator was deferred to Phase 4 as planned. Its oracles are ready: we re-checked the AC-09/AC-10 expected dates by hand (Oct 3, Oct 17, Dec 2, Jan 6 2026, Oct 9 2025), and the calculator will be built test-first against them.
Risk 2 (framework defaults breaking contract conformance) is reduced. 400-not-422 and 401-not-403 are implemented and guarded by tests that demonstrably fail when the default returns (the 422 mutation produced 41 failures). It is not closed until a podmate suite has run against us.
New risk A: specification gaps (ISSUE-01/05/10) make AC-02, AC-08 and AC-16 partly unexecutable through the interface. Resolution: pod v1.1 before Phase 4; fallback is ID-based rewording of the ACs.
New risk C: the course interface depends on pod definitions that do not exist yet (component list, session model, shared plan — ISSUE-11/12/15). If podmates choose differently, coverage numbers are not comparable across teams. Resolution: agree them with the ISSUE-01 batch before Phase 4.
New risk B: the free database expires after 30 days, and cold starts can trip podmate timeouts. Resolution: track the expiry date and decide on a paid plan or recreation before then.

---

## Q8 GenAI Use in This Phase

### Q8.1 Actual GenAI use (one block per teammate)

**[Your name — fill in; others REQUIRE TEAM INPUT]**

Tools and delegation: Claude (Anthropic), used as a coding agent with a shell and a database, generated the contract transcription, service, tests, CI, deployment config, models and this report draft from the Phase 2 specification. This matches the Phase 2 §8.2 plan (scaffolding, tests, docs) but goes further, since it delegated the full implementation rather than scaffolding only. No AI runs in the deployed system.

Verification: Outputs were accepted only on execution evidence: the full suite against a real PostgreSQL service, mutation checks proving the tests can fail, mypy `--strict`, ruff, contract validation, a direct `psql` check of the append-only triggers, and a persistence check that confirms the server process actually changed. Platform facts (Render limits, environment variables, Blueprint syntax) were checked against Render's documentation, not taken from the model [3][4][5]. **[Add: which files you personally reviewed line by line.]**

Correction example: The agent's verification harness once reported a false pass. A cleanup step deleted the PID file while the old server was still running, so the new server failed to bind the port, but the startup health check passed against the stale process, and the tests and persistence restart hit the wrong server. The giveaway was missing evidence: the new log contained no request lines, even though the tests claimed to have made hundreds of requests. The fix made the start script refuse an occupied port and fail if its own process exits, and the re-run confirmed the restart replaced the process (PID 2526 → 2579). A third example came from the cross-team interface: per-session code coverage first used coverage.py's default tracer, which ignores threads that already exist. FastAPI runs our database calls on such threads, so those lines would never have been counted. A 10-line probe exposed it and we switched to the `sysmon` backend (`docs/genai-log.md`, C9). A second example: `pip-audit` showed the agent's default dependency pins carried 14 published advisories (`docs/genai-log.md`, C8).

Agentic principles: We followed contract-first development, black-box tests derived from the specification, evidence before claims, and surfacing ambiguities instead of silently resolving them; nothing was pushed or deployed without human approval. We deviated in one way: the same agent wrote both the code and the tests, so they share one reading of the specification. The independent check is the podmate's suite and human review, and as of this draft neither has happened **[update]**. The model diagrams were also drawn without the Phase 2 images.

---

## Q9 References

[1] U.S. Securities and Exchange Commission. "Form 8-K: Current Report, General Instructions and Item 1.05." https://www.sec.gov/files/form8-k.pdf. Accessed: 2026-10-17.
[2] Office of the Federal Register, National Archives and Records Administration. "17 CFR 240.13a-15, Issuer's Disclosure Controls and Procedures." Electronic Code of Federal Regulations. https://www.ecfr.gov/current/title-17/section-240.13a-15. Accessed: 2026-10-17.
[3] Render. "Blueprint YAML Reference." https://render.com/docs/blueprint-spec. Accessed: 2026-10-17.
[4] Render. "Environment Variables and Secrets — Default environment variables." https://render.com/docs/environment-variables. Accessed: 2026-10-17.
[5] Render. "Deploy for Free." https://render.com/docs/free. Accessed: 2026-10-17.
[6] The PostgreSQL Global Development Group. "TRUNCATE." PostgreSQL 16 Documentation. https://www.postgresql.org/docs/16/sql-truncate.html. Accessed: 2026-10-17.
[7] FastAPI. "Handling Errors." https://fastapi.tiangolo.com/tutorial/handling-errors/. Accessed: 2026-10-17.
[8] Psycopg. "Connection pools." Psycopg 3 Documentation. https://www.psycopg.org/psycopg3/docs/advanced/pool.html. Accessed: 2026-10-17.
[9] OpenAPI Initiative. "OpenAPI Specification v3.1.0." February 15, 2021. https://spec.openapis.org/oas/v3.1.0. Accessed: 2026-10-17.
[10] Ned Batchelder and contributors. "Coverage.py — Configuration reference: [run] core." Coverage.py 7.16 documentation. https://coverage.readthedocs.io/en/latest/config.html. Accessed: 2026-10-18.
[11] Python Software Foundation. "sys.monitoring — Execution event monitoring." Python 3.12 documentation. https://docs.python.org/3.12/library/sys.monitoring.html. Accessed: 2026-10-18.
