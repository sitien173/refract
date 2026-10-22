<!-- refract-shared-version: 1.2.0 -->

# Phase 2 — Journal: Remove parallel readers from the server

## META

- Plan: docs/plans/remove-parallel-readers-dependencies/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 3bcb3445-b34d-49dd-865f-38cb7d7d2427
- Review Job: 8afcd08d-1f9c-474a-b537-841d75170648 FAIL; e09f76b5-337b-468c-a24f-fe4d8a5636fe PASS
- Started: 2026-10-22T18:05:00+07:00
- Finished: 2026-10-22T18:27:00+07:00

## Implementation Response

<!-- Coordinator appends the external response here. -->

# EXTERNAL RESPONSE
## META
- Phase 2 / Started 2026-10-22T18:00:00+07:00 / Finished 2026-10-22T18:02:22+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Partial scheduler and access-class/configuration work was started, but Phase 2 is incomplete and verification fails.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/scheduler.py | Began replacing reader/session admission with one active job per project; dependency readiness retained |
| Modified | server/src/refract/planning.py | Removed derive_access_mode |
| Modified | server/src/refract/drivers.py | Removed supports_verified_read_only |
| Modified | server/src/refract/config.py | Began removing max_project_readers |
| Modified | server/src/refract/runtime.py | Removed reader scheduler argument and access-mode plumbing at some call sites |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-02/notes.md | Recorded partial implementation and failed verification |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-02/journal.md | Recorded this blocked response |
## NOTES
- phase-02/notes.md (## Task 1, ## Task 2)
## SPEC COMPLIANCE
- Meets Spec? NO — implementation is incomplete; pytest reports 126 failed tests, 452 passed, 3 deselected, and the residue check has remaining matches.
## CLARIFICATIONS NEEDED
None; work stopped with the implementation incomplete.
## NEXT
BLOCKED

# EXTERNAL RESPONSE
## META
- Phase 2 / Started 2026-10-22T18:02:22+07:00 / Finished 2026-10-22T18:15:39+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Removed parallel-reader admission and its access-class/configuration surfaces while preserving dependency readiness and terminal-commit release.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/src/refract/scheduler.py | Simplified project admission to one ready job per project, FIFO, bounded by `max_jobs`; retained dependency readiness and completion semantics |
| Modified | server/src/refract/runtime.py | Updated scheduler callers to use `enqueue(job_id, project_id)` |
| Modified | server/src/refract/planning.py | Removed `derive_access_mode` |
| Modified | server/src/refract/drivers.py | Removed `supports_verified_read_only` |
| Modified | server/src/refract/database.py | Removed access-mode validation, job-insert field, and parameter; retained schema/migration column |
| Modified | server/src/refract/models.py | Removed access mode from dashboard job model and removed reader settings update model |
| Modified | server/src/refract/config.py | Removed `max_project_readers` default, supported key, and parser |
| Modified | server/src/refract/dashboard.py | Removed reader settings output and PUT settings handler/route; retained GET |
| Modified | server/tests/test_scheduler.py | Removed reader/barrier/session admission tests; retained/added FIFO, cross-project, dependency and terminal-release coverage |
| Modified | server/tests/test_planning.py | Removed access-class derivation and verified-read-only tests |
| Modified | server/tests/test_execution.py | Removed reader/access-class admission tests and updated capacity/dependency scenarios |
| Modified | server/tests/test_database.py | Removed access-mode insert argument/assertion while retaining dependency persistence coverage |
| Modified | server/tests/test_config.py | Replaced supported-value tests with unsupported daemon setting test |
| Modified | server/tests/test_config_mutation.py | Removed obsolete reader-setting mutation test |
| Modified | server/tests/test_dashboard.py | Removed reader settings/output tests and added a PUT-does-not-succeed test |
| Modified | server/tests/test_server.py | Removed obsolete access-mode arguments in job fixtures |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-02/notes.md | Appended continuation evidence for Tasks 1–4 |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-02/journal.md | Appended completion response |
## NOTES
- phase-02/notes.md (## Task 1 (continuation), ## Task 2 (continuation), ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES — `pytest -q` reports 548 passed, 3 deselected; source residue is limited to retained `database.py` schema/migration lines; `git diff --check` passes.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase 2 / Review fix cycle 1 / Started 2026-10-22T18:15:39+07:00 / Finished 2026-10-22T18:22:29+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Restored retained dependency, custom-argument round-trip, and fallback-plan coverage while removing only Phase 2 access-class assertions.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/tests/test_dashboard.py | Restored as `test_dashboard_job_metadata_preserves_dependencies_and_waiting_reason` |
| Modified | server/tests/test_execution.py | Restored as `test_runtime_submit_persists_dependencies_and_runs_dependent` and `test_submission_preserves_fallback_targets_beyond_attempt_limit` |
| Modified | server/tests/test_planning.py | Restored as `test_custom_target_args_round_trip_in_plan` and `test_pi_native_args_round_trip_in_plan` |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-02/notes.md | Appended review-fix decisions and verification evidence |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-02/journal.md | Appended review-fix response |
## NOTES
- phase-02/notes.md (## Task 2 (fix 1))
## SPEC COMPLIANCE
- Meets Spec? YES — full server pytest: 555 passed, 3 deselected; `git diff --check` passes. No production files changed.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Review Response

<!-- Coordinator appends the independent review response here. -->

## Coordinator Evidence

- Jobs: 3bcb3445 BLOCKED partial; 7d7ddf9a continuation 1 TASK_COMPLETE; 871fb353 fix cycle 1 TASK_COMPLETE.
- Review 8afcd08d FAIL: two Medium findings on deleted mixed-purpose tests. Fixed in e5c0a72 by restoring five tests without access-class assertions.
- Fresh checks: pytest 555 passed, 3 deselected; git diff --check clean; residue only database.py schema and migration lines; dashboard_static residue deferred to Phase 4.
- Review e09f76b5 PASS, no findings.
