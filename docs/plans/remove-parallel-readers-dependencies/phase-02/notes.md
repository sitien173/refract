<!-- refract-shared-version: 1.2.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Began simplifying scheduler dispatch to project-exclusive admission while retaining dependency readiness and the terminal waiter machinery.

### Spec deviations
- Phase remains incomplete; no deviation is claimed as an intentional design choice.

### Tradeoffs accepted
- none

### Assumptions
- Dependency readiness remains in this phase as required by the prompt.

### Follow-ups for human
- Complete the remaining production and test changes in the Phase 2 file set before accepting this phase.

### Test evidence
- `cd server && uv run --extra dev pytest -q`: 452 passed, 126 failed, 3 deselected. Failures include removed scheduler constructor arguments and stale callers/tests, confirming the implementation is incomplete.

## Task 2

### Decisions made
- Removed access-class derivation and the driver's verified-read-only helper; began removing the reader setting from configuration.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Finish `database.py`, models/dashboard/runtime callers, mutation surface, and targeted tests. Preserve the database column/schema migration references for Phase 3.

### Test evidence
- Partial verification at the initial attempt: pytest failed (452 passed, 126 failed, 3 deselected); residue remained. Continuation completed the remaining access-class/configuration removals and verified the full suite: 548 passed, 3 deselected.

## Task 1 (continuation)

### Decisions made
- Scheduler scans pending jobs FIFO and admits the earliest dependency-ready job whose project has no active dispatch, up to `max_jobs`; dependency readiness and `reevaluate` remain.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `uv run --extra dev pytest -q -x`: 548 passed, 3 deselected; scheduler tests cover same-project FIFO, cross-project concurrency, dependency readiness, and release at terminal commit using `complete(signal=False)`.

## Task 2 (continuation)

### Decisions made
- Removed access mode from job creation parameters/insert and job/dashboard models while retaining the schema column and migration reference for Phase 3.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Full Python suite passes; the requested source residue search is limited to retained `database.py` schema/migration lines.

## Task 3

### Decisions made
- Removed the daemon setting from configuration parsing and settings models/output; the dashboard settings route is GET-only and no longer exposes PUT.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Added config rejection coverage for `[daemon].max_project_readers = 2` and dashboard coverage confirming PUT does not succeed; full suite passes.

## Task 4

### Decisions made
- Removed tests specific to reader/access-class/barrier/session-scope admission and the removed reader setting; retained dependency behavior coverage and added the required unsupported-setting and removed-route tests.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q -x`: 548 passed, 3 deselected. Full `pytest -q` verification also passed with the same counts. `git diff --check` passed.

## Task 2 (fix 1)

### Decisions made
- Restored mixed-purpose dependency and execution-plan tests with assertions scoped to behavior retained in Phase 2; removed only access-class assertions and names.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Dependency persistence/readiness and plan argument/fallback preservation remain in scope through Phase 2; Phase 3 removes dependencies.

### Follow-ups for human
- none

### Test evidence
- Restored/renamed tests: `test_dashboard_job_metadata_preserves_dependencies_and_waiting_reason`, `test_runtime_submit_persists_dependencies_and_runs_dependent`, `test_submission_preserves_fallback_targets_beyond_attempt_limit`, `test_custom_target_args_round_trip_in_plan`, and `test_pi_native_args_round_trip_in_plan`.
- Targeted verification: 7 passed. Full suite and `git diff --check` verification recorded after this fix cycle.
