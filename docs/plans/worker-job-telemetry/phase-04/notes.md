<!-- refract-shared-version: 2.0.0 -->

# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Placed normalized telemetry panel directly after the top job-detail grid and before the prompt panel, providing immediate operator visibility.
- Grouped telemetry into explicit Context and Consumption subsections to ensure live context occupancy is never conflated with cumulative job consumption.
- Distinguish unknown null measurements as 'Unavailable' while preserving reported zero counts as numeric '0'.
- Render cache read and cache write tokens dynamically in Consumption whenever supplied.
- Enforce that remaining percentage is strictly unavailable whenever context capacity is null.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added 5 failing tests in `server/web/src/components/JobDetails.test.jsx` asserting normalized telemetry rendering with separated context/consumption, zero vs unavailable distinction, quality/source provenance, missing capacity handling, and historical job safety. Vitest confirmed RED with 5 failures (21 passed, 5 failed). After implementing `TelemetryRow` and the `job-telemetry-panel` in `JobDetails.jsx` and styling in `app.css`, Vitest confirmed GREEN with 26 passed out of 26 in `JobDetails.test.jsx`, and all 237 frontend tests passing across 21 test files.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Reused existing selected-job polling on both canonical (`/dashboard/projects/:projectId/jobs/:jobId`) and legacy (`/dashboard/jobs/:jobId`) routes without adding duplicate timers, telemetry SSE, or dependence on `useJobStream`.
- Retained prior telemetry values during background refresh failure and verified recovery on subsequent poll.
- Guarded against in-flight race conditions when navigating between jobs so late responses cannot mutate current job telemetry.
- Verified that transcript truncation (`stream_status === 'truncated'`) does not interfere with telemetry presentation or polling.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added 3 new tests in `server/web/src/screens/ProjectDetail.test.jsx` and 2 new tests in `server/web/src/integration/dashboard-flow.test.jsx` testing polling telemetry progression to terminal state, failure recovery, late response discard during job switching, legacy route telemetry polling, and transcript truncation resilience. Tests initially timed out / failed (RED) before proper fake timer scoping and routing mock alignment, then all passed (GREEN). `ProjectDetail.test.jsx` passed all 27 tests, `dashboard-flow.test.jsx` passed all 10 tests, and full test suite passed 242 tests across 21 files.
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Added integration coverage verifying that running-to-terminal progression updates telemetry in job result metadata via `finish_job` and is accurately retrieved by dashboard job endpoints.
- Verified that normalized telemetry snapshots in SQLite survive runtime reload across separate `Runtime` lifecycles.
- Verified that transcript retention pruning preserves job result metadata and telemetry while cleaning up event records.
- Verified that historical jobs lacking telemetry metadata return cleanly without fabricated measurements or errors.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added `test_transcript_pruning_preserves_job_telemetry` in `server/tests/test_retention.py` (passed 4/4). Added `test_dashboard_running_to_terminal_telemetry_progression`, `test_dashboard_telemetry_persists_across_runtime_reload`, and `test_dashboard_historical_jobs_without_telemetry_return_cleanly` in `server/tests/test_dashboard.py`. Initial run failed RED with 2 failures (`merge_telemetry` completeness assertion and missing reload app fixture), then passed GREEN (60/60 in `test_dashboard.py`). Full suite run `cd server && uv run pytest` passed with 728 passed, 15 deselected.
- Root cause (bugfix only): - none

## Task 4

### Decisions made
- Restored exact admission sentence in `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`: "At most one job per project runs at a time. Jobs within each project are admitted FIFO, bounded by the global `max_jobs` capacity; jobs in different projects may run concurrently up to that capacity."
- Restored read-only target advice for `consult` and `review` workflows.
- Documented normalized telemetry metadata object in `tool-contract.md`.
- Documented normalized versus legacy semantics, cache accounting, observation/presentation timing, partial totals, backend capability limits, and opt-in probe limitations in `server/README.md` and `server/CLI_ARGUMENTS.md`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `bash plugin/tests/run.sh` initially failed RED on missing admission sentence (line 48 assertion) and profile preset regex match on backticked quality keyword. Once corrected and restored, `bash plugin/tests/run.sh` passed GREEN with session-start tests passed, contract tests passed, and plugin manifest validation passed.
- Root cause (bugfix only): - none

## Task 5

### Decisions made
- Built packaged dashboard assets through standard Vite build config (`npm run build` in `server/web`).
- Verified packaged bundle contains `job-telemetry-panel` and preserved all font/image assets.
- Ran all four required offline verification checks.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Verification checks:
  1. `cd server && uv run pytest` -> 728 passed, 15 deselected in 161.61s.
  2. `cd server/web && npm test` -> 242 passed across 21 test files in 28.33s.
  3. `cd server/web && npm run build -- --outDir /tmp/refract-worker-job-telemetry-build` -> build completed in 3.13s with exit code 0.
  4. `bash plugin/tests/run.sh` -> exit code 0, session-start tests passed, contract tests passed, validation passed.
- Root cause (bugfix only): - none
