# Project Phase 3 — draft answers

Evidence base: local runs on 2026-10-17 05:09 UTC against PostgreSQL 16 + the service at the
working-tree state (not yet committed). Items marked **[NEEDS VERIFICATION]** depend on the
deployment, CI, or pod actions that have not happened yet; **[REQUIRES TEAM INPUT]** needs facts
only the team has. Replace every marker before submitting.

---

## Q1 Delivered Increment

### Q1.1 Increment description

Delivered capability: Through the pod's authenticated common interface, a compliance or incident-response user can now record a cybersecurity incident with its discovery time, attach evidence in the four contract categories, and retrieve the incident with all of its evidence. Every record is persisted in PostgreSQL and is append-only, enforced both by the API (405 on edits/deletes) and by database triggers. Invalid input is rejected with a 400 that names the offending field, and timestamps must carry a UTC offset. Unknown incidents return 404, and missing or wrong API keys return 401. The increment establishes the timestamped evidence trail that the Phase 4 materiality decision and four-business-day deadline will build on. Operations scheduled for Phases 4–5 are routed and authenticated but return 501 NOT_IMPLEMENTED.

Users/stakeholders: incident-response and compliance staff at SEC registrants; disclosure committee (consumer of the evidence record); podmate team and graders (cross-team test clients).
Regulatory provision(s): Form 8-K Item 1.05(a) and Instruction 1 — nature, scope, timing and impact of the incident, and timing of the materiality determination relative to discovery [1]; 17 CFR 240.13a-15(e) disclosure controls (accurate, retained records) [2].

REQ-01 - Create incident │ Status: complete │ Demonstrated by: AC-01
REQ-02 - Invalid incident │ Status: complete │ Demonstrated by: AC-02
If partial: the AC-02 "incident count unchanged" check cannot run through contract v1.0, which has no list operation. It is skipped and logged as ISSUE-01; the behavior itself (nothing is inserted on a 400) is enforced in code by validating before the single INSERT transaction.
REQ-03 - Add evidence │ Status: complete │ Demonstrated by: AC-04, AC-05
REQ-07 - No edits or deletes │ Status: partial │ Demonstrated by: AC-08 (Phase 3 portion: `test_req07_*`)
If partial: covers incidents and evidence; decisions and filings do not exist until Phases 4–5. AC-08's decision-history steps are blocked by ISSUE-05/ISSUE-10.
REQ-13 - Authentication │ Status: partial │ Demonstrated by: AC-14
If partial: API-key enforcement is complete and tested. HTTPS depends on deployment **[NEEDS VERIFICATION: run `test_ac14_served_over_https` against the Render URL]**.
REQ-14 - Errors, reset, formats │ Status: partial │ Demonstrated by: AC-01–AC-05, AC-16
If partial: complete for the Phase 3 operations; Phase 4–5 operations are not implemented yet.
REQ-15 - Persistence and performance │ Status: partial │ Demonstrated by: AC-16
If partial: verified locally (100/100 incidents survive restart; 100% of 200 requests under 1 s, p95 4 ms). The run against the deployed service is pending **[NEEDS VERIFICATION]**.

### Q1.2 Comparison with the Phase 2 plan

Every capability in the Phase 2 §6.1 milestone was implemented: incident and evidence data models, persistent PostgreSQL storage, API-key authentication, `/health`, `POST /incidents`, `GET /incidents/{id}`, evidence, `/reset`, synthetic fixtures (`fixtures/phase3.json`), and automated tests for AC-01–AC-04. We also delivered AC-05, AC-14, the REQ-07 incident portion, and AC-16 persistence/latency checks, because REQ-03, REQ-13 and REQ-15 otherwise had no acceptance evidence. **[NEEDS VERIFICATION: deployed web service — fill in once the Render deploy is live; if it is not live at submission, state that deployment is the undelivered item.]** The pod's *shared* fixture repository was not created; our fixtures live in this repository **[REQUIRES TEAM INPUT: confirm with the podmate team]**. No instructor-required scope changes occurred, and no shared scope was reduced.

---

## Q2 Deployment and Operation

### Q2.1 Deployed web service

The service runs on Render as a Docker web service (Python 3.12 + uvicorn), region Ohio, free plan, with a Render Postgres 16 database, defined in `render.yaml` [3]. Each response carries an `X-Service-Version` header holding the first 12 characters of `RENDER_GIT_COMMIT`, the commit SHA Render deploys [4]. That maps the running version to a commit **[NEEDS VERIFICATION: base URL `https://…onrender.com` and deployed SHA]**. A new version is released by merging to `main`. GitHub Actions runs static checks and the contract suite, and Render's `autoDeployTrigger: checksPass` deploys the commit only after those checks pass [3]. The service is not always on: free web services spin down after 15 idle minutes and take about a minute to wake on the next request [5]. The free database expires 30 days after creation (1 GB, no backups) [5] **[NEEDS VERIFICATION: database creation date → expiry date]**, and workspaces get 750 free instance hours per month [5]. Podmates should send one `GET /health` and allow up to 60 s before timing tests, and should coordinate before running the suite, because every test calls `POST /reset`, which wipes all data.

### Q2.2 Registry and team documentation

Registry entry: **[REQUIRES TEAM INPUT: class registry location]** │ Updated on: **[date]** — entry should list base URL, contract version v1.0, test runner `python -m pytest` with `BASE_URL`/`API_KEY`, and repository link.
Team documentation: `README.md`, `docs/models.md` (+ `docs/diagrams/*.png`), `docs/spec-issues.md`, `openapi/contract.yaml` in `github.com/saachikayadav/incident-clock` │ Updated on: **[date of push]**

### Q2.3 Operational experience supported by observability evidence

The Phase 2 plan (§7.3) held without change. Data persists in PostgreSQL, and status is derived at read time rather than stored. `POST /reset` runs `TRUNCATE … RESTART IDENTITY`, which clears all tables and restarts ID numbering; it bypasses the row-level triggers that otherwise reject any UPDATE or DELETE [6]. `API_KEY` is a Render secret entered once in the dashboard (`sync: false`), and `DATABASE_URL` is injected from the database [3]. Neither is in the repository, and `.env` is git-ignored. Failures are detected through one structured JSON log line per request (`request_id`, `method`, `path`, `status`, `latency_ms`, `error_code`, `version`). The logs also record `startup`, `reset`, and `unhandled_exception` events, and `/health` checks the database and returns 503 if it is unreachable. Request bodies and API keys are never logged. A local test run produced 1,594 request lines. Excerpt **[NEEDS VERIFICATION: replace with lines from the Render log stream after deploy]**:

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

Integration: This is the first increment, so every component is new. A request passes through one middleware, which assigns a request ID, enforces `X-API-Key` (401), times the request and writes the log line. It then reaches a route handler in `app/main.py`, which checks that the incident exists (404). Next, `app/validation.py` checks the body (400) instead of FastAPI's default 422 path [7]. Finally, `Store` (`app/db.py`, psycopg connection pool [8]) writes the record and its history event in one transaction. The `events` table is already populated, so the Phase 5 timeline will need no backfill, and Phase 4 adds a deadline module and a decisions table behind the same handlers.

### Q3.2 Contract changes and pod communication

Contract version at delivery: v1.0 (unchanged; machine-readable transcription in `openapi/contract.yaml` [9]).
Changes since Phase 2: none.
Pod agreement: n/a — proposals ISSUE-01…ISSUE-10 in `docs/spec-issues.md` are to be raised with the pod **[REQUIRES TEAM INPUT: date and channel once raised]**.
Intentional deviations and resolution plan: (1) Operations not yet built return 501 `NOT_IMPLEMENTED` instead of a contract response (ISSUE-09), resolved as Phases 4–5 land. (2) `GET /openapi.yaml` is an extra, unauthenticated route serving the contract file; it is additive and does not change any contract operation. (3) Where the contract is silent we applied documented interim rules: max lengths (ISSUE-02), 404-before-400 order (ISSUE-03), `INVALID_<FIELD>` error codes (ISSUE-04), future `collectedAt` accepted (ISSUE-06), unknown fields ignored (ISSUE-07), and 503 on `/health` (ISSUE-08). We will adopt whatever the pod fixes in v1.1.

---

## Q4 Automated Validation

### Q4.1 Test runner and execution instructions

Base URL override: environment variables only — `BASE_URL=https://<any team> API_KEY=<shared key> python -m pytest` (and `python scripts/operation_status.py`); no test code changes; tests never import the application. The GitHub Actions workflow also accepts a `base_url` input to run the suite against any deployed service. │ Response received: **[NEEDS VERIFICATION: `GET <deployed>/health` → expected `200 {"status":"ok"}`]** (local: `200 {"status":"ok"}`, header `X-Service-Version`) │ Conforms to spec: yes (local; validated against `openapi/contract.yaml` with jsonschema)
Known deviations from the OpenAPI spec: Phase 4–5 operations return 501 (see Q3.2). No deviations in implemented operations.

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

Oracles: Every expected status, field and value comes from the Phase 2 acceptance criteria and §5.2 examples. Response bodies are validated against the contract schemas in `openapi/contract.yaml`, never against the implementation's own output, and timestamps are compared as parsed instants rather than strings. We trust the oracles because they can fail: three deliberately injected defects were each caught. Accepting offset-less timestamps failed 3 tests, returning FastAPI's default 422 failed 41, and validating the body before the 404 check failed 1. After each mutation the code was restored and verified byte-for-byte.

### Q4.3 Regression and static checks

CI run: **[NEEDS VERIFICATION: link to the first green run of `.github/workflows/ci.yml` on `main`]**

Every push and pull request re-runs the complete suite (all Phase 3 tests, and in later phases all earlier ones) against a fresh PostgreSQL 16 service container. Tests are added per phase and never removed, so Phase 3 behavior stays checked as Phases 4–5 change the same handlers. The persistence check and the operation-status probe also run on every build, and the JUnit and status reports are uploaded as artifacts. Render deploys only commits whose checks passed (`checksPass`), so a regression cannot reach the deployed service through the normal release path.

### Q4.4 Static checks

CI run: **[NEEDS VERIFICATION: same link]**

CI runs these checks on every push and PR: ruff lint (including security rules `S`), the ruff format check, mypy `--strict`, `openapi-spec-validator` on the contract file, and `pip-audit` on the runtime dependencies. They all run in a `static` job that the contract-test job depends on, so a failing static check stops testing, and through `checksPass` it also stops deployment. Blocking merges additionally requires enabling branch protection on `main` **[REQUIRES TEAM INPUT: enable "require status checks"]**. `pip-audit` has already paid off: it found 14 published advisories against the initial `starlette 0.46.2` pin, which we resolved by upgrading before the first deploy.

### Q4.5 Test results against the deployed system

Run date/time: **[NEEDS VERIFICATION: deployed run]** │ Version tested: **[tag/SHA]**
Tests run: **[#]** │ Passed: **[#]** │ Failed: **[#]** │ Skipped: **[#]**

Reference result, local service on the same code, 2026-10-17 05:09 UTC: 86 collected, 84 passed, 0 failed, 2 skipped. Contract-only (`-m "not provisional"`): 80 passed, 2 skipped. Expected deployed result: 85 passed, 1 skipped, because the HTTPS test runs once BASE_URL is https.

Skipped: `test_ac02_rejected_request_creates_nothing` │ Classification: specification │ Cause: AC-02's count check needs a list operation absent from contract v1.0 (ISSUE-01) │ Plan: pod decides between adding `GET /incidents` and rewording AC-02 before Phase 4.
Skipped (local only): `test_ac14_served_over_https` │ Classification: test environment │ Cause: local target is http │ Plan: runs automatically against the deployed URL.

---

## Q5 Updated System Models

### Q5.1 Model updates

A1 Architecture and data flow (component) │ Changed: yes │ What changed and why: Phase 2 §7.1 showed separate API, application/service and deadline-service layers. As built, the route handlers call validation and the Store directly, and the deadline module does not exist yet, so it is drawn dashed as "planned". We added Render, the log stream, and the CI → deploy path with commit-SHA traceability. │ Location: `docs/models.md` §A1, `docs/diagrams/a1-architecture.png`
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

**[REQUIRES TEAM INPUT — no cross-team run has happened yet; do not submit placeholders as results.]** To run: our suite against them is `BASE_URL=<their URL> API_KEY=<their key> python -m pytest --junitxml=reports/cross.xml`, plus `scripts/operation_status.py` for the per-operation report. Run `-m "not provisional"` as well, so that contract failures can be told apart from failures on unresolved spec items. They can run their suite against our deployed URL with the shared key.

Our tests → **[team]** service │ Date: […] │ Run/passed: [#/#] │ Main problem and owner: […]
**[team]** tests → our service │ Date: […] │ Run/passed: [#/#] │ Main problem and owner: […]
Coverage per direction: system-model coverage = operations exercised ÷ 10 contract operations (from `operation_status.md`); component coverage = which of middleware / handlers / validation / Store were hit (all four for Phase 3 operations); code coverage only for our own service (`coverage run -m uvicorn …` during their run) **[NEEDS VERIFICATION]**.

### Q6.2 Specification issues discovered

Issue: AC-02 and AC-16 (REQ-02, REQ-14, REQ-15) require counting incidents ("count unchanged", "all 100 remain", "no incidents remain after reset"), but contract v1.0 has no operation that lists or counts incidents.
Effect: The count half of AC-02 cannot be evaluated through the common interface by any team. Our suite skips it with a reason and verifies AC-16 through 404s on known IDs instead, and a podmate suite may count differently or not at all, so results are not comparable.
Pod decision or plan: **[REQUIRES TEAM INPUT: decision and date]**. We propose either adding `GET /incidents` (v1.1) or rewording both ACs to ID-based checks, decided before Phase 4 starts. Related gaps to bring to the same meeting: AC-08 targets "the old decision" and "decision history", but the contract has no URL for either (ISSUE-05/10), and max field lengths are still unset (ISSUE-02).

---

## Q7 Status, Limitations and Next-Phase Adjustments

### Q7.1 What changed and what remains incomplete

Changed since Phase 2:
- Service built and tested: incident creation/retrieval and evidence (REQ-01, REQ-02, REQ-03; AC-01–AC-05).
- API-key auth and contract error format on every route (REQ-13, REQ-14; AC-03, AC-14).
- Append-only storage enforced by DB triggers; 405 on incident edits/deletes (REQ-07 partial; AC-08 partial).
- Persistence across restart and latency verified (REQ-15; AC-16), plus reset (REQ-14).
- CI with static checks, contract suite, persistence check, and Render `checksPass` deploy gating.

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
LIM-08 │ The Docker image has not been built yet: Docker Hub was unreachable from the build sandbox. The identical runtime (same files, pins, CMD and port) passes the full suite. │ Affects: deployment │ Severity: medium until first Render build
Workaround for podmates: none │ Target phase: 3 (first deploy) **[NEEDS VERIFICATION]**

### Q7.3 Adjustments to next phase milestone

The Phase 4 milestone (§6.2) holds unchanged in capability: decisions, state rules, the deadline calculator, and deadline status for REQ-04/05/08/09/10. Its tests depend on two pod decisions, though. AC-15 needs the 409 check to have a defined place in the check order (ISSUE-03), and the decision tests need the error-code catalogue (ISSUE-04), so both need pod agreement before Phase 4 tests are written. No sequencing change is needed: the `events` table and derived-status design already accommodate decisions.

Risk 1 (deadline arithmetic: Eastern Time, day-0 rule, holidays) remains open, because the calculator was deferred to Phase 4 as planned. Its oracles are ready: we re-checked the AC-09/AC-10 expected dates by hand (Oct 3, Oct 17, Dec 2, Jan 6 2026, Oct 9 2025), and the calculator will be built test-first against them.
Risk 2 (framework defaults breaking contract conformance) is reduced. 400-not-422 and 401-not-403 are implemented and guarded by tests that demonstrably fail when the default returns (the 422 mutation produced 41 failures). It is not closed until a podmate suite has run against us.
New risk A: specification gaps (ISSUE-01/05/10) make AC-02, AC-08 and AC-16 partly unexecutable through the interface. Resolution: pod v1.1 before Phase 4; fallback is ID-based rewording of the ACs.
New risk B: the free database expires after 30 days, and cold starts can trip podmate timeouts. Resolution: track the expiry date and decide on a paid plan or recreation before then.

---

## Q8 GenAI Use in This Phase

### Q8.1 Actual GenAI use (one block per teammate)

**[Your name — fill in; others REQUIRE TEAM INPUT]**

Tools and delegation: Claude (Anthropic), used as a coding agent with a shell and a database, generated the contract transcription, service, tests, CI, deployment config, models and this report draft from the Phase 2 specification. This matches the Phase 2 §8.2 plan (scaffolding, tests, docs) but goes further, since it delegated the full implementation rather than scaffolding only. No AI runs in the deployed system.

Verification: Outputs were accepted only on execution evidence: the full suite against a real PostgreSQL service, mutation checks proving the tests can fail, mypy `--strict`, ruff, contract validation, a direct `psql` check of the append-only triggers, and a persistence check that confirms the server process actually changed. Platform facts (Render limits, environment variables, Blueprint syntax) were checked against Render's documentation, not taken from the model [3][4][5]. **[Add: which files you personally reviewed line by line.]**

Correction example: The agent's verification harness once reported a false pass. A cleanup step deleted the PID file while the old server was still running, so the new server failed to bind the port, but the startup health check passed against the stale process, and the tests and persistence restart hit the wrong server. The giveaway was missing evidence: the new log contained no request lines, even though the tests claimed to have made hundreds of requests. The fix made the start script refuse an occupied port and fail if its own process exits, and the re-run confirmed the restart replaced the process (PID 2526 → 2579). A second example: `pip-audit` showed the agent's default dependency pins carried 14 published advisories (`docs/genai-log.md`, C8).

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
