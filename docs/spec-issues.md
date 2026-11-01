# Specification issues found while implementing contract v1.0 (Phases 3–4)

Contract v1.0 (Phase 2 report §5.1/5.2, transcribed in `openapi/contract.yaml`) is **unchanged**.
None of the items below has pod agreement yet (Phase 3 items ISSUE-01…16; Phase 4 items ISSUE-17…23 at the end). Each lists this team's interim behavior so
cross-team results can be interpreted, and the tests that depend on it are marked
`@pytest.mark.provisional` (or skipped, for ISSUE-01).

| ID | Affects | Ambiguity / gap | Interim behavior (this team) | Effect on cross-team testing | Proposed resolution |
|---|---|---|---|---|---|
| ISSUE-01 | AC-02, AC-16 | Both ACs check incident **counts** ("count unchanged", "100 remain", "none remain after reset"), but the contract has no list operation, so a black-box client cannot count. | AC-02 count check is **skipped** with a reason. AC-16 reset is checked via 404 on previously created IDs; persistence via GET on each of 100 known IDs. | Count half of AC-02 is untestable on any implementation. | v1.1: add `GET /incidents` → `200 {incidents: IncidentSummary[]}`, **or** reword AC-02/AC-16 to the ID-based checks above. |
| ISSUE-02 | REQ-02, §5.2 | Max lengths for `title`/`description` are "agreed by both teams" but no number is recorded; other text fields have no limit. | title 200, description 5000, reporterName 200, summary 5000, source 500. | A podmate with other limits will fail `test_ac02_length_limit_boundary` (and vice versa). | Pod fixes numbers in v1.1. |
| ISSUE-03 | Model 4, all incident-scoped POSTs | Order of 404 vs 400 when the incident is unknown **and** the body is invalid is not stated in text. | 401 → 405 → 404 → 400 (→ 409 in Phase 4). | Frameworks that validate bodies first return 400. | Confirm order in v1.1 text. |
| ISSUE-04 | REQ-14, §5.2 | Only one error code (`INVALID_DECISION`) is defined; other codes are free text. | Field errors `INVALID_<FIELD>` (e.g. `INVALID_DISCOVERED_AT`), `INVALID_BODY`, `UNAUTHORIZED`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `NOT_IMPLEMENTED`, `INTERNAL_ERROR`. | Tests assert status + `{error, message}` shape only, and "names the field" via message **or** code. | Publish a code catalogue in v1.1. |
| ISSUE-05 | REQ-07, AC-08 | 405 applies to "edit or delete requests", but evidence/decisions/filings have no item URLs, so there is nothing to `PUT`/`DELETE`. AC-08 sends them "to the old decision". | 405 on `PUT/PATCH/DELETE /incidents/{id}` and on any non-POST method to the collection paths. Unknown item paths return 404. | AC-08 cannot be executed as written. | v1.1: either add `.../decisions/{decisionId}` read path (then 405 on PUT/DELETE) or reword AC-08 to the incident path. |
| ISSUE-06 | REQ-03 | Future check is stated for `discoveredAt` and `determinedAt`; `collectedAt` is silent. | `collectedAt` in the future is accepted. | Divergence possible. | Decide in v1.1. |
| ISSUE-07 | All POSTs | Behavior for unknown extra JSON fields is unspecified. | Ignored. | Divergence possible. | Decide in v1.1 (ignore recommended). |
| ISSUE-08 | REQ-13 `/health` | Contract lists no error for `/health`. | 503 `{status: "DATABASE_UNAVAILABLE"}` when the database is unreachable (body still matches `{status}`). | None for healthy services. | Note in v1.1. |
| ISSUE-09 | Phase sequencing | How a service should answer operations scheduled for later phases is unspecified. | Auth and 404 enforced; otherwise 501 `NOT_IMPLEMENTED`. | Cross-team suites will see 501, not a contract violation of an implemented op. | Pod agrees 501 for phased delivery. |
| ISSUE-10 | AC-08 | "GET the decision history" — no operation returns history (GET incident returns only `currentDecision`; timeline returns event refs only). | — (Phase 5) | AC-08 unverifiable as written. | Resolve with ISSUE-05 before Phase 5. |

## Course cross-team testing interface (added 2026-10-18)

The course interface (tester `/test/setup|run|report`, system `/test/setup|report`) leaves these
items to the pod specification. None is agreed yet; interim choices below are implemented and
described in `openapi/system-test-interface.yaml` and `openapi/tester.yaml`.

| ID | Item the pod must define | Interim behavior (this team) | Why it matters |
|---|---|---|---|
| ISSUE-11 | **Component list** for component coverage | The 10 operations of contract v1.0; an operation counts when a request reached its own logic (response not 401/404/405/501). | Teams that pick different lists report incomparable component coverage. |
| ISSUE-12 | **Session model**: how project requests identify the prepared state; concurrency | Contract v1.0 has no session field, so one session is active per system; `/test/setup` clears project data and supersedes the previous session (its final coverage stays readable). Runs against one target must not overlap. | Two testers hitting the same system at once would wipe each other's data (every test also calls `POST /reset`). |
| ISSUE-13 | **Starting data** in system `setup` | None defined; `{}` sent and accepted. | Needed once Phase 4 tests require pre-loaded incidents. |
| ISSUE-14 | **Access**: how a tester obtains a target's key | System `/test/*` and project endpoints require the shared pod key in `X-API-Key`. Tester endpoints are open, but the tester only sends a key to targets listed in its `TARGETS` setting; other `target_url` values get 400. | Keys must not go in URLs or the registry; each team must register podmate URLs in its tester. |
| ISSUE-15 | **Which tests form the shared plan** | Our tester runs `tests/` with `-m "not provisional"`, so tests of behaviour the pod has not fixed (ISSUE-02/03/07) never count against a podmate. | Prevents failing another team on our own interim choices. |
| ISSUE-16 | **Project-call time limits and retries** | 60 s per request (covers free-plan cold start), no retries; tester setup waits up to 120 s for system setup; run limit 600 s. | The course spec leaves these to the pod. |

## Phase 4 (decisions, deadlines, filing — added 2026-10-30)

Found while implementing REQ-04/05/08/09/10/11 against contract v1.0. None has pod agreement yet.

| ID | Affects | Ambiguity / gap | Interim behavior (this team) | Effect on cross-team testing | Proposed resolution |
|---|---|---|---|---|---|
| ISSUE-17 | REQ-09, Q5.3, Q8.1 | "The pod's shared holiday list" is referenced but no list file exists, and its year range is not stated. | U.S. federal holidays per 5 U.S.C. 6103 as observed, 2023–2027, frozen in `app/deadline.py` and published as `fixtures/holidays.json`. Determinations outside 2023-01-01..2027-12-20 → 400 `INVALID_DETERMINED_AT`. Inauguration Day excluded. | A team using a different list or range diverges on deadlines near those dates; all AC-09/AC-10 dates agree. | Pod adopts `fixtures/holidays.json` (or its own) as the shared file in v1.1. |
| ISSUE-18 | REQ-11, §5.2 | `filedAt` has no future or ordering rule (e.g. before `determinedAt`), and the Regulation S-T 5:30 pm ET cut-off is not mentioned. | Any RFC 3339 `filedAt` with offset accepted; timeliness uses its Eastern Time date only (Q3.3: "late is based on the filing date the user enters"). | Divergence possible for future or pre-determination filings. | Decide in v1.1. |
| ISSUE-19 | REQ-10, REQ-11 | Business days late are undefined when the action falls on a weekend/holiday right after the deadline (e.g. deadline Fri, as_of or filing Sat: 0 business days elapsed, yet late). | OVERDUE/LATE count = business days in (deadline, date], minimum 1. | Only weekend/holiday dates immediately after a deadline; no AC uses them. | Fix the counting rule in v1.1. |
| ISSUE-20 | REQ-08, Model 1 | REQ-08 lists no 409 for a new (non-correction) decision while `NOT_MATERIAL`; our redrawn Model 1 shows `NOT_MATERIAL → MATERIAL` only through a correction. | Follows REQ-08 text: a new decision on a `NOT_MATERIAL` incident is accepted (201). Test is `provisional`. | A team following Model 1 returns 409. | Pod confirms in v1.1 which source wins. |
| ISSUE-21 | REQ-04, §5.2 | Duplicate entries in `evidenceIds`, and max lengths for `decidedBy`, `rationale`, `accessionNumber`, are unspecified. | Duplicates → 400 `INVALID_EVIDENCE_IDS`; limits 200 / 5000 / 100 characters. Tests `provisional`. | Divergence possible. | Decide in v1.1 with ISSUE-02. |
| ISSUE-22 | REQ-10, §5.2 | `DeadlineStatus` for a `FILED` incident: the enum has no FILED value, and "null when not applicable" is the only guidance. | `NOT_APPLICABLE`, `deadline: null`, `businessDays: 0` once filed (the deadline remains on `currentDecision`). | A team returning the deadline or PENDING after filing diverges. | Decide in v1.1. |
| ISSUE-23 | REQ-08, §6 phasing | AC-15's FILED and OPEN cases need `POST /filing`, which §6.2 schedules for Phase 5, so AC-15 cannot be completed in Phase 4 as planned. | We delivered `POST /filing` (REQ-11) in Phase 4. | A podmate that kept filing in Phase 5 returns 501 for these cases until then. | Pod notes the dependency; no contract change. |
