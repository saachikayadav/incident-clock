# Project Phase 4 — draft answers

Evidence base: commit `d386109` on a local service against PostgreSQL 16, 2026-10-30 18:49 UTC
(full suite, tester → system grader sequence, operation-status probes, persistence check, mutation
checks). The increment was developed locally as `d386109` and pushed to `main` as `851b418`
(2026-11-01, CI passed); the deployed service has run it since. Updated 2026-11-19 with the
deployed version, CI links, the database expiry and recreation, and the web frontend.
**[DEPLOY]** marks values that need the deployed API key to collect; **[TEAM]** marks facts only
the team or pod has. Replace every marker before submitting.

---

## Q1 Delivered Increment

### Q1.1 Increment description

Delivered capability: Through the authenticated common interface, a disclosure reviewer can now record a human materiality decision (MATERIAL or NOT_MATERIAL) that cites evidence from the same incident, and the incident status changes as Model 1 defines. A MATERIAL decision gets its Form 8-K deadline: the fourth business day after the Eastern Time determination date, skipping weekends and federal holidays [1, General Instruction B.1][2][3]. A user can query deadline status at any `as_of` time (PENDING with business days left, OVERDUE with business days late, or NOT_APPLICABLE), and record an 8-K filing that is marked ON_TIME or LATE. Workflow rules (REQ-08) return 409 and change nothing: a second decision while MATERIAL_PENDING_FILING, any decision once FILED, and a filing outside MATERIAL_PENDING_FILING. Invalid decisions, such as a determination before discovery or in the future, or evidence from another incident, return 400 and are not stored. The system never makes or suggests a decision; status changes only when a person posts one.

Users/stakeholders: disclosure committee and compliance staff at SEC registrants (decision record, deadline tracking); incident-response staff (evidence cited by decisions); podmate team and graders (cross-team testing).
Regulatory provision(s): Form 8-K Item 1.05(a) (materiality is determined by the registrant) and General Instruction B.1 (four business days after the determination) [1]; federal holidays per 5 U.S.C. 6103 as the business-day calendar [2][3].

REQ-04 - Record materiality decision │ Status: complete │ Demonstrated by: AC-06, AC-07
REQ-05 - Invalid decision │ Status: complete │ Demonstrated by: AC-06
REQ-08 - State rules │ Status: partial │ Demonstrated by: AC-15
If partial: all three AC-15 cases and every other decision/filing rule are delivered. The correction rules (409 on a correction while FILED) arrive with corrections in Phase 5.
REQ-09 - Deadline calculation │ Status: complete │ Demonstrated by: AC-09, AC-10
REQ-10 - Deadline status │ Status: complete │ Demonstrated by: AC-07, AC-11 (deadline-status part)
REQ-11 - Record filing │ Status: complete │ Demonstrated by: AC-11 (filing part), AC-15
If partial: n/a. Delivered one phase early because AC-15's FILED and OPEN cases cannot run without it (ISSUE-23).
REQ-07 - No edits or deletes │ Status: partial │ Demonstrated by: AC-08 (Phase 3–4 portion: `test_req07_*`)
If partial: 405 and database triggers now cover decisions and filings; AC-08's correction-history steps need corrections (Phase 5) and ISSUE-05/10.
REQ-14 - Errors, reset, formats │ Status: partial │ Demonstrated by: AC-01–AC-07, AC-09–AC-11, AC-15, AC-16
If partial: complete for every delivered operation; corrections and timeline still return 501.

### Q1.2 Comparison with the Phase 2 plan

Everything in the Phase 4 milestone (Phase 2, Section 6.2) was delivered: the decision data model and endpoint, the state-transition logic, the business-day and holiday calculator, the deadline-status endpoint, expanded fixtures (`fixtures/phase4.json`, `fixtures/holidays.json`), and automated AC-06, AC-07, AC-09 and AC-10 tests plus state-conflict and deadline-status tests. Beyond the plan, we delivered `POST /filing` (REQ-11) and AC-11 and AC-15 tests. The reason is that AC-15 cannot be run without a FILED incident, and filing timeliness reuses the same calculator. Not delivered: AC-07's code-inspection half is a manual checklist item, not an automated test, as Phase 2 Q4.1 specified. The demonstration (create → evidence → MATERIAL decision → MATERIAL_PENDING_FILING with deadline → deadline status at a fixed `as_of`) passes locally and on the deployed service (2026-11-19 run, Q4.5: `test_ac06_*`, `test_ac09_*` and `test_ac11_*` cover each step). No instructor-required scope changes occurred, and no shared scope was reduced.

---

## Q2 Deployment and Operation

### Q2.1 Deployed web service

As in Phase 3: two Docker web services (Python 3.12 + uvicorn) defined in `render.yaml`, region Ohio, free plan, with a Render Postgres 16 database [4]. New: `render.yaml` also defines a third web service, `incident-clock-frontend` (Python, gunicorn), which serves the browser UI in `frontend/` and calls the system API server-side with the API key (see LIM-15, LIM-16). It is not part of the pod contract and not needed for cross-team testing. It went live on 2026-11-19 at `https://incident-clock-frontend.onrender.com`, served by gunicorn, and its page reported "API connected" to the system service. System `https://incident-clock.onrender.com`; tester `https://incident-clock-tester.onrender.com`. Every response's `X-Service-Version` header and every tester report's `tester_version` hold the first 12 characters of `RENDER_GIT_COMMIT`, which maps the running service to a commit [5]; the Phase 4 commit is `851b418` (local `d386109` before the push). On 2026-11-19 the header showed `68a54844c9e8`, the current `main`: Phase 4 plus the web frontend, its Render service, and these documentation updates. The API code is unchanged since `851b418`. A release is a merge to `main`. CI then runs static checks, deadline unit tests and the contract suite, and Render deploys only after those checks pass (`autoDeployTrigger: checksPass`) [4]. The schema change ships with the code, because the service applies `schema.sql` (`CREATE … IF NOT EXISTS`) on startup. The new tables are created on the first boot of `d386109`, and existing incidents and evidence are kept. The service is not always on: free services spin down after 15 idle minutes and take about a minute to wake [6]. The free database expires 30 days after creation [6]. Ours was created 2026-10-18 and expired on 2026-11-17: the service then failed its startup database check and never answered `/health`, while the tester (no database) stayed up. On 2026-11-19 we deleted it, recreated `incident-clock-db` from the Blueprint, and redeployed; `/health` returned `{"status":"ok"}`. The schema was applied on startup, but all earlier incidents, evidence, decisions and filings were lost, and the new database expires around 2026-12-19 **[TEAM: upgrade, or recreate before 2026-12-19; see LIM-02]**. Podmates should send `GET /health` and wait for 200 before timing anything, announce runs in the pod channel (every test calls `POST /reset`), and fetch tester reports promptly (in-memory).

### Q2.2 Registry and team documentation

Registry entry: **[TEAM: class registry location]** │ Updated on: **[date]**. The entry is unchanged in URLs (system and tester base URLs above). Update its notes to say "Phase 4: decisions, deadline-status (`as_of`), filing implemented; corrections and timeline return 501".
Team documentation: `README.md` (status by requirement, operations, local run instructions for the API and the web frontend), `docs/models.md` + `docs/diagrams/*.png` (A1, T1, M1–M4), `docs/spec-issues.md` (ISSUE-17…23 new), `fixtures/holidays.json`, `openapi/contract.yaml` in `github.com/saachikayadav/incident-clock` │ Updated on: 2026-11-01 (Phase 4, `851b418`); 2026-11-19 (web frontend and README run instructions, `e1efa65`)

### Q2.3 Operational experience supported by observability evidence

The Phase 2 §7.3 plan still holds; Phase 4 added the deadline signals it called for. Data persists in PostgreSQL, and status is still derived, not stored. Each MATERIAL decision's deadline is computed once and stored on the decision row, so later holiday-list edits cannot silently move a recorded deadline. `POST /reset` truncates all six project tables with `RESTART IDENTITY`, the only path that bypasses the append-only triggers [7]. Secrets are unchanged: `API_KEY` is a Render secret (`sync: false`), `DATABASE_URL` is injected from the database, and neither is in the repository [4]. Two new failure signals were added. Every decision writes a `decision_recorded` line with its Eastern Time determination date and computed deadline, so a disputed deadline can be traced to its inputs. State conflicts are visible as `error_code: STATE_CONFLICT` on the request line. The persistence check now also verifies that a MATERIAL decision and its stored deadline survive a restart (local: 100/100 incidents, decision and deadline intact). Excerpt from the local run at `d386109` **[DEPLOY: replace with Render log-stream lines]**:

```
{"ts": "2026-10-30T18:49:21.034Z", "level": "info", "event": "decision_recorded", "incident_id": "INC-001", "decision_id": "DEC-001", "decision": "MATERIAL", "determined_date_et": "2025-09-29", "deadline": "2025-10-03"}
{"ts": "2026-10-30T18:49:20.991Z", "level": "warning", "event": "request", "method": "POST", "path": "/incidents/INC-001/filing", "status": 409, "latency_ms": 3.1, "error_code": "STATE_CONFLICT", "version": "d3861096561e"}
{"ts": "2026-10-30T18:49:18.899Z", "level": "info", "event": "request", "method": "GET", "path": "/incidents/INC-001/deadline-status", "status": 200, "latency_ms": 1.9, "error_code": null, "version": "d3861096561e"}
```

---

## Q3 Implementation and Interface Conformance

### Q3.1 Operation status
(Generated by `scripts/operation_status.py` from live probes against the deployed service, `https://incident-clock.onrender.com`, version `68a54844c9e8`, 2026-11-19. It gives the same result as the earlier local run at `d386109`.)

GET /health │ Requirement(s): REQ-13 │ Implemented: yes
Success responses conform: yes │ Error responses conform: n/a (contract lists none; 503 `{status}` if the DB is down)

POST /incidents │ Requirement(s): REQ-01, REQ-02 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400, 401)

POST /incidents/{incidentId}/evidence │ Requirement(s): REQ-03 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400, 401, 404)

POST /incidents/{incidentId}/decisions │ Requirement(s): REQ-04, REQ-05, REQ-08, REQ-09 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400, 401, 404, 409)

POST /incidents/{incidentId}/corrections │ Requirement(s): REQ-06, REQ-08, REQ-09 │ Implemented: no (Phase 5)
Success responses conform: n/a (501) │ Error responses conform: 401, 404 yes; 400, 409 not yet

GET /incidents/{incidentId} │ Requirement(s): REQ-01, REQ-03, REQ-04, REQ-06 │ Implemented: yes
Success responses conform: yes (`currentDecision` and `filing` now populated; superseded history arrives with REQ-06) │ Error responses conform: yes (401, 404)

GET /incidents/{incidentId}/deadline-status │ Requirement(s): REQ-09, REQ-10 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400 on malformed `as_of`, 401, 404)

POST /incidents/{incidentId}/filing │ Requirement(s): REQ-08, REQ-11 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (400, 401, 404, 409)

GET /incidents/{incidentId}/timeline │ Requirement(s): REQ-12 │ Implemented: no (Phase 5)
Success responses conform: n/a (501) │ Error responses conform: yes (401, 404)

POST /reset │ Requirement(s): REQ-14 │ Implemented: yes
Success responses conform: yes │ Error responses conform: yes (401)

Course testing interface (`/test/setup`, `/test/report`): unchanged since Phase 3; `tester_tests/test_system_interface.py` 11/11 pass.

Integration: The new handlers sit behind the same middleware (401, request log) and the same 404 → 400 checks as Phase 3. Field validation, including `determinedAt` ≥ `discoveredAt` and not in the future, now runs before any write. The new `app/deadline.py` module is the single place that converts a timestamp to its Eastern Time date and counts business days [8]. It serves the decision handler (deadline), deadline-status (PENDING/OVERDUE) and filing (ON_TIME/LATE), as Phase 2 Q7.2 Decision 1 planned. `Store.record_decision` and `Store.record_filing` each run one transaction. They lock the incident row (`SELECT … FOR UPDATE`, which does not fire the append-only UPDATE trigger [9]), check evidence ownership (400), then check state (409), then insert the record and its history event. Concurrent requests on one incident therefore cannot both pass the state check. The new tables `decisions`, `decision_evidence` and `filings` carry the same append-only triggers. A composite foreign key makes the database itself reject a decision that cites another incident's evidence.

### Q3.2 Contract changes and pod communication

Contract version at delivery: v1.0 (unchanged; `openapi/contract.yaml` [10]).
Changes since Phase 2: none.
Pod agreement: n/a. Phase 4 interpretation questions ISSUE-17…23 (`docs/spec-issues.md`) are to be raised together with the open Phase 3 batch (ISSUE-01…16) **[TEAM: date and channel once raised]**.
Intentional deviations and resolution plan: (1) Corrections and timeline return 501 `NOT_IMPLEMENTED` until Phase 5 (ISSUE-09). (2) `POST /filing` is live one phase before the §6.2 plan; this adds capability and changes no contract behavior (ISSUE-23). (3) We apply interim rules where v1.0 is silent and mark the tests `provisional`: holiday list range 2023–2027 (ISSUE-17), no future or order rule on `filedAt` (ISSUE-18), minimum of 1 business day late (ISSUE-19), new decisions allowed on NOT_MATERIAL incidents per REQ-08 (ISSUE-20), duplicate `evidenceIds` rejected (ISSUE-21), and NOT_APPLICABLE after filing (ISSUE-22). We adopt whatever the pod fixes in v1.1.

---

## Q4 Automated Validation

### Q4.1 Test runner and execution instructions

Base URL override: unchanged. `POST <our tester>/test/setup {"target_url": "<registered pod system URL>"}` then `POST /test/run {"session_id"}`, with no code changes. Directly: `BASE_URL=<system> API_KEY=<key> python -m pytest`, or `scripts/cross_team_run.py --tester … --target …` for the grader sequence. │ Response received: local, 2026-10-30 18:49 UTC, commit `d386109`: `POST /test/setup {"target_url": "http://127.0.0.1:8000"}` → `201 {"session_id": "ca5b8b1a-1396-4b7d-9922-542695395334"}`; `POST /test/run` → `200`, 140 results (138 pass, 2 skip), coverage code 547/622, component 8/10, system 14/16 **[DEPLOY: repeat against `https://incident-clock-tester.onrender.com` → `https://incident-clock.onrender.com` and paste]** │ Conforms to spec: yes. The report validates against `openapi/tester.yaml`, and every new response validates against the contract schemas (`DecisionCreated`, `DeadlineStatus`, `FilingCreated`, `Incident` with `currentDecision`/`filing`).
Known deviations from the OpenAPI spec: corrections and timeline return 501 (Q3.2). Tester reports carry the four additional fields documented in Phase 3. No deviations in required fields or status codes.

### Q4.2 Tests for new functionality

AC-06 │ Requirement(s): REQ-04, REQ-05
Test(s): `test_ac06_complete_decision_stored_and_status_material_pending`, `test_ac06_not_material_decision_has_no_deadline`, `test_ac06_multiple_evidence_ids_kept_in_order` │ Type: success │ Automated: yes
Test(s): `test_ac06_determination_before_discovery_rejected_and_not_stored` (the AC case), `test_ac06_contract_invalid_decision_example` (§5.2, asserts `INVALID_DECISION`), `test_ac06_evidence_from_another_incident_rejected`, `test_ac06_invalid_decision_rejected_and_not_stored` ×10 (unknown/empty/non-array evidence IDs, bad enum, null, offset-less, future, unparseable `determinedAt`, empty `decidedBy`/`rationale`), `test_ac06_missing_decision_field_rejected` ×5 │ Type: failure │ Automated: yes
Test(s): `test_ac06_determination_equal_to_discovery_accepted`, `test_ac06_duplicate_evidence_ids_rejected` (provisional, ISSUE-21), `test_ac06_unknown_incident_checked_before_body` (provisional, ISSUE-03) │ Type: boundary │ Automated: yes

AC-07 │ Requirement(s): REQ-04, REQ-10
Test(s): `test_ac07_severe_evidence_without_decision_stays_open` (status OPEN, deadline status NOT_APPLICABLE with null deadline) │ Type: success │ Automated: yes; the code-inspection half is manual (checklist: no code path writes a decision except `POST /decisions` with a human-supplied body)

AC-09 │ Requirement(s): REQ-09
Test(s): `test_ac09_monday_determination_due_friday` (deadline compared in the decision response, `GET` incident and deadline-status) │ Type: success │ Automated: yes

AC-10 │ Requirement(s): REQ-09
Test(s): `test_ac10_weekend_and_holiday_deadlines` ×4 (Columbus Day, Thanksgiving, New Year's Day, Saturday) │ Type: boundary │ Automated: yes
Test(s): `test_ac10_eastern_time_date_is_day_zero` ×4 (UTC/ET date split on both sides of midnight, after DST end, Veterans Day) │ Type: boundary │ Automated: yes
Test(s): `unit_tests/test_deadline.py` (26: holiday list vs. statute, every determination day 2023-01-01..2027-12-20 vs. a naive counter, DST date conversion, out-of-range) │ Type: success / boundary │ Automated: yes (CI static job)

AC-11 (delivered early) │ Requirement(s): REQ-10, REQ-11
Test(s): `test_ac11_no_filing_overdue_one_business_day`, `test_ac11_filed_on_deadline_on_time`, `test_ac11_filed_next_business_day_late_by_one` (the three AC cases), `test_ac11_contract_example_pending_one_day` (§5.2), `test_ac11_not_material_is_not_applicable`, `test_ac11_filed_incident_deadline_status_not_applicable`, `test_ac11_as_of_defaults_to_now` │ Type: success │ Automated: yes
Test(s): `test_ac11_deadline_status_boundaries` ×5 (4 days left, 1 left, 0 on the deadline, Saturday after, 6 late across Columbus Day) │ Type: boundary │ Automated: yes
Test(s): `test_ac11_invalid_as_of_400` ×4, `test_ac11_invalid_filing_rejected_and_not_stored` ×4 │ Type: failure │ Automated: yes

AC-15 │ Requirement(s): REQ-08
Test(s): `test_ac15_new_decision_while_material_pending_filing_409`, `test_ac15_decision_while_filed_409`, `test_ac15_filing_while_open_409` (the three AC cases, each comparing the full incident before and after), `test_ac15_filing_while_not_material_409`, `test_ac15_second_filing_while_filed_409` │ Type: failure │ Automated: yes
Test(s): `test_ac15_evidence_still_accepted_after_filing` │ Type: success │ Automated: yes
Test(s): `test_ac15_new_decision_after_not_material_allowed` (ISSUE-20), `test_ac15_invalid_body_on_filed_incident_is_400_not_409`, `test_ac15_foreign_evidence_on_pending_incident_is_400_not_409` (ISSUE-03) │ Type: boundary │ Automated: yes (provisional)

AC-08 (Phase 4 portion) │ Requirement(s): REQ-07
Test(s): `test_req07_decision_and_filing_edit_or_delete_405` ×6 (PUT/PATCH/DELETE on `/decisions` and `/filing`, record unchanged; provisional, ISSUE-05) │ Type: failure │ Automated: yes

Oracles: every expected date and count comes from the Phase 2 acceptance criteria (AC-09, AC-10, AC-11) and the §5.2 examples, copied into `fixtures/phase4.json` and checked by hand before any calculator code existed. Three independent checks back them. The unit tests recompute the holiday list from the statutory rules in 5 U.S.C. 6103 instead of importing ours [2]. A naive day-by-day counter agrees with the calculator on every determination date from 2023 to 2027. Response bodies are validated against the contract schemas, not against our own output. The tests also demonstrably fail on the defects they target, as five injected mutations showed. Counting the determination date as day 1 caused 19 failures. Using the UTC date instead of the Eastern date caused 4. Ignoring holidays caused 5. Removing the MATERIAL_PENDING_FILING 409 caused 1. Removing the application's evidence-ownership check caused 1: the database foreign key still rejected the request, as a 500.

### Q4.3 Regression and static checks

CI run: Phase 4 commit `851b418`, 2026-11-01, success: https://github.com/saachikayadav/incident-clock/actions/runs/41352112845. Current `main` `e1efa65`, 2026-11-19, success: https://github.com/saachikayadav/incident-clock/actions/runs/44633327147

Every push and pull request re-runs the complete suite against a fresh PostgreSQL 16 container. This includes all 86 Phase 3 contract tests unchanged alongside the 69 new Phase 4 tests, the persistence check (now including a decision), the operation-status probe, the system `/test/*` checks, and a full tester → system run. After the Phase 4 code changes and before any new test was added, the unchanged Phase 3 suite passed against the modified service (84 pass, 2 skip, identical to Phase 3); it was re-run after every later change. Render deploys only commits whose checks passed (`checksPass`) [4], so a regression cannot reach the deployed service through the normal release path.

### Q4.4 Static checks

CI run: same runs as Q4.3 (the `static` job).

Unchanged from Phase 3, with one addition: ruff lint (including security rules `S`) and format check, mypy `--strict` (now also over `unit_tests/`), `openapi-spec-validator` on all three API documents, `pip-audit` on both dependency sets, tester self-tests, and **new: the deadline unit tests**. All run in the `static` job, which the contract-test job depends on, so a failing check stops testing and, through `checksPass`, deployment. Ruff's `S608` rule flagged a dynamically built SQL string (the optional `FOR UPDATE` clause) during this phase, and we replaced it with two literal queries. Branch protection is not enabled: on 2026-11-19 GitHub reported `main` as unprotected with no required status checks. A pull request with failing checks can therefore still be merged, although `checksPass` keeps such a commit from deploying **[TEAM: enable "Require status checks to pass" on `main`]**.

### Q4.5 Test results against the deployed system

Command: `BASE_URL=https://incident-clock.onrender.com API_KEY=<deployed key> python -m pytest` (full suite, including provisional tests), run after the database was recreated.
Run date/time: 2026-11-19 23:38 UTC (18:38 ET) │ Version tested: `68a54844c9e8` (`X-Service-Version`)
Tests run: 155 │ Passed: 154 │ Failed: 0 │ Skipped: 1 │ Duration: 59.8 s

This is exactly the expected deployed result. `test_ac14_served_over_https` ran and passed, which confirms the run targeted the HTTPS deployment rather than a local service. The same day, `scripts/operation_status.py` against the deployed service matched Q3.1 line for line.

Reference result at `d386109`, local service, 2026-10-30 18:49 UTC: full suite 155 collected, 153 passed, 0 failed, 2 skipped; contract-only (`-m "not provisional"`): 138 passed, 2 skipped; unit tests 26/26. Expected deployed result: full suite 154 passed, 1 skipped, because the HTTPS test runs against an https URL (confirmed above). Through the tester (non-provisional plan, 140 tests): 139 pass, 1 skip.

Skipped: `test_ac02_rejected_request_creates_nothing` │ Classification: specification │ Cause: AC-02's count check needs a list operation absent from contract v1.0 (ISSUE-01) │ Plan: still waiting on a pod decision; proposed for v1.1 with the Phase 4 batch, before Phase 5 tests are written.

---

## Q5 Updated System Models

### Q5.1 Model updates

M3 Deadline calculation and status (activity) │ Changed: yes (new as built) │ What changed and why: Phase 3 only restated the rule. Now drawn from `app/deadline.py`: Eastern Time day 0 (DST via zoneinfo), supported date range (400 outside it), the four-business-day loop, the PENDING/OVERDUE/NOT_APPLICABLE branches, and filing ON_TIME/LATE with the minimum-of-1 rule (ISSUE-19). │ Location: `docs/models.md` §M3, `docs/diagrams/m3-deadline-calculation.png`
M1 Incident status (state machine) │ Changed: yes │ What changed and why: transitions out of OPEN, NOT_MATERIAL → MATERIAL by a new decision (REQ-08 text, ISSUE-20) and MATERIAL_PENDING_FILING → FILED are now implemented, so the "planned" labels are gone. Every REQ-08 409 is drawn as a self-loop, evidence (201) and edits (405) are noted as allowed in every state, and corrections are a note marked Phase 5. │ Location: §M1, `m1-incident-status.png`
M2 Information model (ER) │ Changed: yes │ What changed and why: generated from `app/schema.sql`. It adds `decisions` (stored deadline, CHECK deadline-iff-MATERIAL, `corrects_seq` reserved for Phase 5), `decision_evidence` with the composite FK to `evidence (seq, incident_seq)`, and `filings` (one per incident). Triggers now cover six tables. │ Location: §M2, `m2-information-model.png`
M4 Request check order (activity) │ Changed: yes │ What changed and why: the 501 branch is now only corrections/timeline. It adds the transaction: row lock → evidence ownership (400) → state (409) → insert, and `as_of` validation. │ Location: §M4, `m4-check-order.png`
A1 Architecture and data flow (component) │ Changed: yes │ What changed and why: the dashed "planned deadline module" is now the real `deadline.py`, called by the route handlers. The database box lists the new tables, and a dashed box marks the Phase 5 operations. Updated 2026-11-19: adds the `incident-clock-frontend` web service (browser → Flask → system API with the key), derived from `frontend/app.py` and `render.yaml`. │ Location: §A1, `a1-architecture.png`
T1 Cross-team test session (sequence) │ Changed: no │ What changed and why: the tester flow is unchanged; the test plan simply contains more tests. │ Location: §T1, `t1-test-session.png`

### Q5.2 Model-implementation consistency

Each model was redrawn from the code rather than from the plan. M2 comes from `schema.sql`, M3 from `deadline.py`, M1 from `status_of()` and the state checks in `Store`, and M4 from the handler and Store order. All are Mermaid source in `docs/models.md`, rendered to PNG in the same commit as the code. Two models are also checked by tests. Every number M3 produces is pinned by the AC-09/10/11 and unit tests. The provisional tests `test_ac15_invalid_body_on_filed_incident_is_400_not_409` and `test_ac15_foreign_evidence_on_pending_incident_is_400_not_409` fail if the code departs from M4's order. One divergence was found and corrected in the code, not the model. While drawing M4, the first implementation checked the 409 state rule before the evidence-ownership 400, which contradicted M4's rule that every 400 precedes every 409 (ISSUE-03). We reordered `Store.record_decision` and added the second test (GenAI log C15). One divergence from Phase 2 remains open, recorded as ISSUE-20 rather than resolved unilaterally. Our Model 1 drawing showed NOT_MATERIAL → MATERIAL only via a correction, while REQ-08 lists no 409 there, and the code follows REQ-08. **[TEAM: compare M1 against the original Phase 2 Model 1 image (Screenshot 214411/214354) and add who walked through the models.]**

---

## Q6 Pod Cross-Team Readiness

### Q6.1 Cross-team test

**[TEAM + DEPLOY: this section needs the runs.]** Procedure (same as Phase 3, no code changes): announce in the pod channel, then `python scripts/cross_team_run.py --tester https://incident-clock-tester.onrender.com --target https://incident-api-356019173418.us-central1.run.app`, and ask the podmates to run their suite against `https://incident-clock.onrender.com`. Saved reports go to `reports/cross-team/`. Copy `coverage.code`, `coverage.component` and `coverage.system` from each report.

Our tests → **[podmate team]** service │ Date: […] │ Run/passed: [#/#] │ Coverage: code […], component [./10], system [./16] │ Main problem and owner: […]
**[podmate team]** tests → our service │ Date: […] │ Run/passed: [#/#] │ Coverage: […] │ Main problem and owner: […]

What to expect so failures are classified correctly: our Phase 4 tests call `POST /filing` for AC-11 and AC-15 (ISSUE-23). If the podmates kept filing for Phase 5, those tests fail with 501 against them. That is a phasing difference, not a defect. Their result for our Phase 3 behaviour should be unchanged (Phase 3: 48/48). Expected own-system baseline on the deployed tester: 139 pass, 1 skip, component 8/10, system 14/16.

### Q6.2 Specification issues discovered

Issue: REQ-09 and Q5.3 rely on "the pod's shared holiday list", but no list file exists and its year range is unstated (ISSUE-17). Related: REQ-10/REQ-11 do not define business days late when the date falls on a weekend or holiday just after the deadline (ISSUE-19).
Effect: Both teams agree on every AC-09/AC-10 date, which use only standard federal holidays. A team that adds Inauguration Day or covers different years, though, will diverge on deadlines near those dates, and a weekend filing after a Friday deadline can come back as LATE/0 on one service and LATE/1 on the other. Our implementation freezes the federal list for 2023–2027 (`fixtures/holidays.json`), rejects determinations outside that range with 400, and counts a minimum of 1 day late.
Pod decision or plan: **[TEAM: decision and date]**. We propose that the pod adopt `fixtures/holidays.json` as the shared file and the minimum-of-1 rule in v1.1, decided together with ISSUE-01/05/10 before Phase 5 tests are written. Also for the same meeting: whether a new decision on a NOT_MATERIAL incident is allowed (REQ-08 vs. Model 1, ISSUE-20), and what deadline-status returns once FILED (ISSUE-22).

---

## Q7 Status, Limitations and Next-Phase Adjustments

### Q7.1 What changed and what remains incomplete

Changed since Phase 2 (Phase 4 increment):
- Human materiality decisions with evidence citation and validation (REQ-04, REQ-05; AC-06, AC-07).
- Deadline calculator in its own module: Eastern Time day 0, federal holidays 2023–2027, stored deadline (REQ-09; AC-09, AC-10).
- Deadline status with `as_of`: PENDING, OVERDUE, NOT_APPLICABLE (REQ-10; AC-07, AC-11).
- Filing with ON_TIME/LATE and business days late, delivered early (REQ-11; AC-11).
- REQ-08 state rules with row locking, and append-only triggers on decisions and filings (REQ-08, REQ-07; AC-15, AC-08 partial).
- Web frontend (`frontend/`, Flask): create an incident, find one by ID, view it with its evidence, and add evidence. It enforces REQ-14 timestamps on input (explicit UTC offset, never assumed), shows times in UTC with Eastern Time, shows live character limits, has no edit or delete controls (REQ-07), and keeps the API key on the server. It uses only the pod contract, so the API is unchanged. Deployable as `incident-clock-frontend` via `render.yaml`.

Remaining incomplete:
- Corrections and decision history (REQ-06; AC-08 history steps, blocked also on ISSUE-05/10) — Phase 5.
- Timeline and evidence summary (REQ-12; AC-12, AC-13) — Phase 5.
- Correction-related state rules (REQ-08: correction while FILED) — Phase 5.
- AC-02 count check (ISSUE-01) and AC-07/AC-14 inspection halves (manual).
- Tester-mediated run against the deployed service (Q4.1) and the cross-team runs (Q6.1). The direct deployed suite run is done (Q4.5).
- The web frontend covers only Phase 3 operations; decisions, deadline status and filing are available through the API and `/docs`, but not yet in the UI (LIM-15).

### Q7.2 Known limitations and defects

LIM-01 │ Free-plan cold start: sleeps after 15 min idle; first request takes ~1 min │ Affects: REQ-15, all operations │ Severity: medium
Workaround for podmates: `GET /health` and wait for 200 before timing │ Target phase: 6
LIM-02 │ Free Postgres expires 30 days after creation. It expired on 2026-11-17 and was recreated on 2026-11-19 (empty); the new one expires around 2026-12-19, and all data is lost again then │ Affects: REQ-15, every operation │ Severity: high
Workaround for podmates: do not rely on data surviving past 2026-12-19; re-create test data after a reset │ Target phase: 5 (upgrade to a paid plan, or recreate before 2026-12-19)
LIM-03 │ Corrections and timeline return 501 │ Affects: REQ-06, REQ-12 │ Severity: high (expected)
Workaround for podmates: exclude `ac08`/`ac12`/`ac13` cases │ Target phase: 5
LIM-12 │ Deadlines only for determinations 2023-01-01..2027-12-20; otherwise 400 `INVALID_DETERMINED_AT` │ Affects: REQ-09, `POST /decisions` │ Severity: low
Workaround for podmates: use 2023–2027 dates (all ACs use 2025) │ Target phase: 6 (extend list yearly)
LIM-13 │ Interim Phase 4 interpretations: no rule on `filedAt` (future or before determination accepted), minimum 1 day late, NOT_APPLICABLE after filing, duplicate `evidenceIds` rejected │ Affects: REQ-08, REQ-10, REQ-11 │ Severity: low
Workaround for podmates: run `-m "not provisional"`; see ISSUE-18…22 │ Target phase: 5 (after pod v1.1)
LIM-14 │ `filedAt` timeliness ignores the Regulation S-T 5:30 pm ET cut-off; a filing at 6 pm ET on the deadline day counts ON_TIME │ Affects: REQ-11 │ Severity: low (follows Phase 2 Q3.3: "late is based on the filing date the user enters") │ Workaround for podmates: none │ Target phase: pod decision (ISSUE-18)
LIM-15 │ The web frontend covers create incident, view incident and add evidence only; no decision, deadline-status or filing screens, and no incident list (contract has no list operation, ISSUE-01; "Recent incidents" is a per-browser cookie) │ Affects: usability, not the pod contract │ Severity: low
Workaround for podmates: use the API or `/docs` for Phase 4 operations │ Target phase: 5
LIM-16 │ The deployed web frontend has no login and holds the API key server-side, so anyone with its URL can create incidents and add evidence │ Affects: REQ-13 │ Severity: medium (synthetic data only)
Workaround for podmates: none needed; do not share the frontend URL outside the pod │ Target phase: 5 (password-protect the frontend, or require each user to enter the key)
LIM-04 │ `POST /reset` deletes everything for every key holder │ Affects: REQ-14 │ Severity: medium
Workaround for podmates: announce runs; never test concurrently │ Target phase: 6
LIM-05 │ Phase 3 interim interpretations (lengths, check order, error codes, unknown fields, future `collectedAt`) │ Affects: REQ-02, REQ-03, REQ-14 │ Severity: low
Workaround for podmates: `-m "not provisional"` │ Target phase: 5 (after pod v1.1)
LIM-06 │ Single shared API key, no rotation, no rate limiting │ Affects: REQ-13 │ Severity: low (synthetic data only)
Workaround for podmates: none │ Target phase: 6
LIM-07 │ `GET /incidents/{id}` returns all evidence without pagination │ Affects: REQ-15 at large counts │ Severity: low
Workaround for podmates: none needed at AC-16 scale │ Target phase: 6
LIM-09 │ Tester sessions and reports are in memory; lost on restart or spin-down │ Affects: course interface │ Severity: medium
Workaround for podmates: fetch `/test/report` right after a run │ Target phase: 6
LIM-10 │ One active test session per system; overlapping runs interfere │ Affects: course interface, REQ-14 │ Severity: medium
Workaround for podmates: one run per target at a time │ Target phase: pod decision (ISSUE-12)
LIM-11 │ Code coverage is line coverage only and is lost on a mid-session restart │ Affects: coverage reporting │ Severity: low
Workaround for podmates: none │ Target phase: 6

### Q7.3 Adjustments to next phase milestone

The Phase 5 milestone (§6.3) holds, with one change in sequencing and no change in shared scope. Filing (REQ-11) is already done, so Phase 5 is corrections (REQ-06), the timeline and evidence summary (REQ-12), and completing REQ-07/REQ-08/REQ-14. No pod agreement is needed for this, because it changes only our order of work. If the podmates kept filing in Phase 5, cross-team AC-11/AC-15 results will differ until they deliver it (ISSUE-23). The schema already reserves `decisions.corrects_seq`, and the current-decision query already excludes corrected decisions, so corrections need no migration of existing rows. A correction's new `determinedAt` recomputes the deadline through the same `deadline.py` call.

Risk 1 (deadline arithmetic: Eastern Time, day-0 rule, holidays) is reduced. Every AC-09/AC-10 date passes. The calculator agrees with an independent naive counter on all 1,815 determination days from 2023 to 2027, and the holiday list matches the statutory rules. Mutations of each rule were caught (19, 4 and 5 failures). What remains is cross-team agreement on the list (ISSUE-17) and the late-count edge (ISSUE-19), which a podmate run will settle.
Risk 2 (framework defaults breaking conformance) is reduced further: all new 400/409 bodies validate against the contract `Error` schema, and the 400-before-409 order is tested. It is not closed until a podmate suite exercises the Phase 4 operations.
New risk D: the database expires 30 days after creation (LIM-02). It materialized: the database expired on 2026-11-17 and the deployed service was down until we recreated it on 2026-11-19, losing all data. The new one expires around 2026-12-19. Resolution: move to a paid instance, or recreate before then and re-run the persistence check **[TEAM: decide before 2026-12-19]**.
New risk E: corrections can move a deadline after a filing exists or after it has become overdue, and REQ-06/REQ-08 do not say whether a correction is allowed while MATERIAL_PENDING_FILING once overdue. Resolution: raise with the pod with ISSUE-05/10 before Phase 5 tests are written.
Remaining from Phase 3: New risk A (ISSUE-01/05/10 spec gaps) and New risk C (course-interface definitions, ISSUE-11/12/15) are still unresolved and need the same pod meeting.

---

## Q8 GenAI Use in This Phase

### Q8.1 Actual GenAI use (one block per teammate)

**[Your name — check and edit; other teammates: REQUIRES TEAM INPUT]**

Tools and delegation: Claude (Anthropic), working as a coding agent with a shell and a local PostgreSQL, implemented the whole Phase 4 increment. That covers the deadline module, the decision and filing handlers and schema, 69 contract tests and 26 unit tests, the updated models and PNGs, the spec-issue list, and this report draft. The inputs were the repository and the graded Phase 2 report. As in Phase 3, this goes beyond the Phase 2 §8.2 plan of scaffolding, tests and docs, because the implementation itself was delegated. No AI runs in the deployed system.

Verification: Outputs were accepted only on execution evidence. That meant the full suite on PostgreSQL 16 (153 pass, 2 skip), the Phase 3 suite re-run unchanged, five mutation checks, ruff and mypy `--strict`, and direct `psql` attempts to UPDATE or DELETE the new tables, which the triggers rejected. A `psql` insert of a cross-incident evidence link was also rejected by the composite FK. The deadline logic was checked against the AC-09/10/11 dates from the Phase 2 text, against a holiday list recomputed independently from the statute, and against a naive counter over every day from 2023 to 2027. **[Add: which files you reviewed yourself — at minimum `app/deadline.py` and `fixtures/phase4.json` against Phase 2 §4.1.]**

Correction example: The first version of `Store.record_decision` checked the state rule (409) before checking that cited evidence belongs to the incident (400). A request that was both state-invalid and cited foreign evidence therefore got 409, which contradicts Model 4's rule that every 400 precedes every 409. No test caught it, because no test combined the two conditions. It surfaced when the M4 diagram was redrawn from the code and the arrows disagreed with the stated order. The checks were reordered, and a provisional test now pins the order (GenAI log C15). A second example: the Mermaid render step failed silently because the headless browser download was blocked, which would have left the Phase 3 PNGs contradicting the updated models. Unchanged file timestamps gave it away (C16).

Agentic principles: We followed contract-first and test-first work: the AC-09/10/11 oracles were fixed in fixtures before the calculator existed. We used evidence before claims, including mutation checks that prove the tests can fail, and surfaced spec ambiguities as ISSUE-17…23 instead of silently resolving them. The agent stated up front that the Phase 2 AC text was missing rather than inventing test inputs. Nothing was pushed or deployed by the agent. The deviation from Phase 3 remains: one agent wrote both the code and its tests, so they share one reading of the spec. Holiday-list and calendar errors are guarded by the statute-derived cross-check, but interpretation errors are not. The podmates' independent suite, and human review of `deadline.py`, are the real check, and as of this draft neither has happened for Phase 4 **[update]**.

---

## Q9 References

[1] U.S. Securities and Exchange Commission. "Form 8-K: Current Report, General Instructions (B.1) and Item 1.05." https://www.sec.gov/files/form8-k.pdf. Accessed: 2026-10-30.
[2] Office of the Law Revision Counsel, U.S. House of Representatives. "5 U.S.C. 6103 — Holidays." United States Code. https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title5-section6103&num=0&edition=prelim. Accessed: 2026-10-30.
[3] U.S. Office of Personnel Management. "Federal Holidays." https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/. Accessed: 2026-10-30.
[4] Render. "Blueprint YAML Reference." https://render.com/docs/blueprint-spec. Accessed: 2026-10-17.
[5] Render. "Environment Variables and Secrets — Default environment variables." https://render.com/docs/environment-variables. Accessed: 2026-10-17.
[6] Render. "Deploy for Free." https://render.com/docs/free. Accessed: 2026-10-17.
[7] The PostgreSQL Global Development Group. "TRUNCATE." PostgreSQL 16 Documentation. https://www.postgresql.org/docs/16/sql-truncate.html. Accessed: 2026-10-17.
[8] Python Software Foundation. "zoneinfo — IANA time zone support." Python 3.12 documentation. https://docs.python.org/3.12/library/zoneinfo.html. Accessed: 2026-10-30.
[9] The PostgreSQL Global Development Group. "SELECT — The Locking Clause." PostgreSQL 16 Documentation. https://www.postgresql.org/docs/16/sql-select.html#SQL-FOR-UPDATE-SHARE. Accessed: 2026-10-30.
[10] OpenAPI Initiative. "OpenAPI Specification v3.1.0." February 15, 2021. https://spec.openapis.org/oas/v3.1.0. Accessed: 2026-10-17.

(Verify [2] and [3] open before submitting — they could not be fetched from this workspace.)
