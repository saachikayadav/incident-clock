# Design requirements and the tests that evaluate them (coverage.model)

Design version: **IncidentClock design v5.0 (docs/models.md, Phase 5)**. Generated from `tester/design_requirements.json` by
`scripts/design_mapping.py`; do not edit by hand. The tester reports `coverage.model` from this
mapping only when it tests this team's own system (`OWN_SYSTEM_URLS`). A requirement counts as
covered when at least one mapped test was executed and evaluated (pass or fail).

| ID | Model | Design requirement | Tests |
|---|---|---|---|
| DR-01 | M1 | A new incident is OPEN. | `test_ac01_create_returns_201_with_id_and_open_status`<br>`test_ac07_severe_evidence_without_decision_stays_open` |
| DR-02 | M1 | OPEN + MATERIAL decision -> MATERIAL_PENDING_FILING with a deadline. | `test_ac06_complete_decision_stored_and_status_material_pending` |
| DR-03 | M1 | OPEN + NOT_MATERIAL decision -> NOT_MATERIAL with no deadline; a later decision is still accepted (ISSUE-20). | `test_ac06_not_material_decision_has_no_deadline`<br>`test_ac15_new_decision_after_not_material_allowed` |
| DR-04 | M1 | MATERIAL_PENDING_FILING + new (non-correction) decision -> 409, nothing changes. | `test_ac15_new_decision_while_material_pending_filing_409` |
| DR-05 | M1 | MATERIAL_PENDING_FILING + filing -> FILED. | `test_ac11_filed_on_deadline_on_time` |
| DR-06 | M1 | FILED rejects decisions, corrections and filings with 409. | `test_ac15_decision_while_filed_409`<br>`test_ac15_second_filing_while_filed_409`<br>`test_req08_correction_while_filed_409` |
| DR-07 | M1 | A filing outside MATERIAL_PENDING_FILING (OPEN, NOT_MATERIAL) -> 409. | `test_ac15_filing_while_open_409`<br>`test_ac15_filing_while_not_material_409` |
| DR-08 | M1 | A correction of the current decision re-derives status (MATERIAL <-> NOT_MATERIAL). | `test_req06_correction_to_not_material_changes_status_and_clears_deadline`<br>`test_req06_correction_to_material_uses_new_determination_for_deadline` |
| DR-09 | M1 | Evidence is accepted in every status. | `test_ac15_evidence_still_accepted_after_filing` |
| DR-10 | M2 | Records are append-only: edit/delete requests return 405 and change nothing. | `test_req07_incident_edit_or_delete_405`<br>`test_req07_decision_and_filing_edit_or_delete_405`<br>`test_req07_corrections_edit_or_delete_405`<br>`test_req12_timeline_other_methods_405` |
| DR-11 | M2 | A decision or correction cites only evidence of its own incident (400). | `test_ac06_evidence_from_another_incident_rejected`<br>`test_req06_correction_citing_foreign_evidence_400` |
| DR-12 | M2 | A correction supersedes the current decision; the superseded decision stays in the history unchanged. | `test_ac08_correction_keeps_old_decision_in_history`<br>`test_req06_corrections_chain_latest_is_current` |
| DR-13 | M2 | Every action writes one event; the timeline lists them in recording order. | `test_ac12_five_events_in_recorded_order`<br>`test_req12_full_lifecycle_events_in_recorded_order`<br>`test_req12_new_incident_timeline` |
| DR-14 | M3 | Deadline = 4th business day after the determination date, skipping weekends and listed federal holidays. | `test_ac09_monday_determination_due_friday`<br>`test_ac10_weekend_and_holiday_deadlines` |
| DR-15 | M3 | Day 0 is the Eastern Time calendar date of determinedAt. | `test_ac10_eastern_time_date_is_day_zero` |
| DR-16 | M3 | Deadline status is PENDING/OVERDUE with business-day counts, or NOT_APPLICABLE, evaluated at as_of. | `test_ac11_no_filing_overdue_one_business_day`<br>`test_ac11_deadline_status_boundaries`<br>`test_ac11_not_material_is_not_applicable` |
| DR-17 | M3 | Filing timeliness is ON_TIME on or before the deadline (ET date of filedAt), else LATE with business days late. | `test_ac11_filed_on_deadline_on_time`<br>`test_ac11_filed_next_business_day_late_by_one` |
| DR-18 | M3 | A correction recomputes the deadline from its own determination time; status and filing timeliness use it. | `test_req06_corrected_deadline_drives_deadline_status`<br>`test_req06_filing_after_correction_is_judged_against_corrected_deadline` |
| DR-19 | M4 | Every endpoint except the public ones requires X-API-Key (401 first). | `test_ac14_missing_key_401`<br>`test_ac14_wrong_key_401`<br>`test_ac14_health_needs_no_key` |
| DR-20 | M4 | An unknown incident is 404 before any body validation. | `test_ac03_other_incident_operations_unknown_id_404`<br>`test_ac03_unknown_incident_checked_before_body`<br>`test_ac06_unknown_incident_checked_before_body` |
| DR-21 | M4 | Every 400 (fields, evidence ownership) precedes 409. | `test_ac15_invalid_body_on_filed_incident_is_400_not_409`<br>`test_ac15_foreign_evidence_on_pending_incident_is_400_not_409`<br>`test_req06_invalid_body_on_filed_incident_is_400_not_409` |
| DR-22 | M4 | Invalid input returns 400 {error, message} naming the field, and stores nothing. | `test_ac02_pod_fixture_cases_rejected`<br>`test_ac04_invalid_evidence_rejected_and_not_stored`<br>`test_ac06_invalid_decision_rejected_and_not_stored`<br>`test_req06_invalid_correction_rejected_and_not_stored`<br>`test_ac11_invalid_filing_rejected_and_not_stored` |
| DR-23 | M4 | correctsDecisionId: not a decision of this incident -> 400; an already-superseded decision -> 409 (ISSUE-24). | `test_req06_corrects_unknown_decision_400`<br>`test_req06_corrects_decision_of_another_incident_400`<br>`test_req06_correction_on_open_incident_400`<br>`test_req06_correcting_a_superseded_decision_409` |
| DR-24 | A1 | POST /reset clears all project data; old IDs no longer resolve. | `test_ac16_reset_clears_all_records`<br>`test_ac03_reset_ids_do_not_resolve` |
| DR-25 | A1 | The timeline summary gives evidence counts by category and ET calendar days from discovery to the current determination. | `test_ac13_evidence_summary`<br>`test_req12_evidence_counts_by_category`<br>`test_req12_days_count_eastern_calendar_dates`<br>`test_req12_days_follow_the_current_decision` |

Total: 25 design requirements.
