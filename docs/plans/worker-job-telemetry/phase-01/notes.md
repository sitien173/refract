<!-- refract-shared-version: 2.0.0 -->

# Phase 1 — Decision Notes

<!--
Worker Notes template. Copy to docs/plans/<slug>/phase-<NN>/notes.md, fill the
heading, then append one `## Task <M>` block per task. Keep the file; never
overwrite earlier task blocks. Empty sub-sections = `- none`. Every task gets a
block even if all `none`.
-->


## Task 1

### Decisions made
- Defined strict typed Pydantic models for `Measurement`, `TelemetryData`, `TelemetryAttribution`, and `CompletedAttemptsAggregate`.
- Restricted `source` to an allowlist of interface identifiers and explicitly rejected file paths and raw JSON payloads.
- Strictly rejected booleans, negative integers, floats for token counts, and non-finite percentages.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server && uv run pytest tests/test_telemetry.py` failed with `ModuleNotFoundError: No module named 'refract.telemetry'`, then passed 9 tests after implementing `refract/telemetry.py`.
- Root cause (bugfix only): none


## Task 2

### Decisions made
- Implemented `merge_job_telemetry` on `Database` to transactionally merge incoming telemetry without overwriting unrelated metadata fields.
- Protected terminal jobs from stale running telemetry updates in `merge_job_telemetry`.
- Updated `_finish` to merge terminal metadata with any existing running telemetry so terminal writes cannot wipe out telemetry observations.
- Updated `reset_retry` to accumulate prior attempt consumption into `completed_attempts`, clear the context snapshot, and increment the attribution attempt number.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server && uv run pytest tests/test_database.py -k telemetry` failed with `AttributeError: 'Database' object has no attribute 'merge_job_telemetry'`, then passed all tests after implementing `merge_job_telemetry`, `_finish`, and `reset_retry` updates.
- Root cause (bugfix only): none


## Task 3

### Decisions made
- In `TargetExecutor`, routed `telemetry.updated` observations through `TelemetryAccumulator` and persisted them immediately via `database.merge_job_telemetry` before transcript recording in `StreamRecorder`.
- Handled non-blocking emission on the current loop thread in `StreamBridge` to avoid deadlocks when drivers or test doubles run on the asyncio loop thread.
- Assigned actual persisted `attempt` numbers (retrieved via `record_job_attempt`) and explicit `invocation` numbers (1 for initial, 2 for reconstruct, 3 for fresh) to all telemetry observations and event payloads.
- Retained partial telemetry observations across job cancellation, failure, timeout, and interruption by saving telemetry into exception metadata and terminal metadata.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server && uv run pytest tests/test_execution.py -k "test_telemetry_updated_routes"` failed with `AssertionError: assert None is not None`, then all 5 execution telemetry tests passed after routing `telemetry.updated` through execution and wiring attempt/invocation identities.
- Root cause (bugfix only): none


## Task 4

### Decisions made
- Updated `Runtime.live_result_metadata` to preserve `"telemetry"` when present in stored job metadata, leaving historical jobs without telemetry intact.
- Updated MCP `job_wait` in `server.py` to include live metadata with `"telemetry"` for running jobs as well as terminal paginated responses.
- Verified dashboard direct job read (`/dashboard/api/jobs/{job_id}`) and project job listing (`/dashboard/api/projects/{project_id}/jobs`) expose the telemetry object.
- Validated `job_wait` input schema stability in MCP schema contract tests.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server && uv run pytest tests/test_runtime.py -k live_result_metadata tests/test_server.py -k test_job_wait_running tests/test_dashboard.py -k test_dashboard_job_reads` confirmed characterization and verified additive telemetry exposure across runtime, MCP, and dashboard.
- Root cause (bugfix only): none


## Fix 1

### Decisions made
- In `database.py`, acquired write transaction (`BEGIN IMMEDIATE`) before reading state or metadata in `merge_job_telemetry`, `_finish`, and `reset_retry` to prevent read-modify-write race conditions.
- In `database.py`, validated and sanitized every incoming telemetry payload via `TelemetryData.model_validate` before persistence; rejected unvalidated initial dicts and fallback writes.
- In `telemetry.py`, added strict observation validation before mutating accumulator state; rejected boolean values, negative integers, non-integer floats, and malformed counts.
- In `telemetry.py`, tracked availability per individual measurement instead of converting missing fields to reported zero; preserved explicit `Measurement.unavailable()` on null contributions.
- In `telemetry.py`, enforced observation ordering using observation timestamps and prevented stale or out-of-order observations from overwriting newer response records.
- In `telemetry.py`, added `finalize_invocation` to reject post-finalization observations and protect committed response records.
- In `telemetry.py`, retained truthful provenance in snapshot generation by preserving observation quality, source, and exact latest timestamp without refreshing to `utc_now()`.
- In `telemetry.py` and `execution.py`, preserved context invalidation across session recovery; rejected incompatible prior context from older invocations upon recovery start.
- In `execution.py`, dispatched cumulative totals before testing cache fields, avoiding discarding cumulative input and output tokens.
- In `execution.py`, tracked consumption availability per invocation; marked totals incomplete (`partial`) when recovery or retry invocations did not observe consumption.
- In `execution.py`, ensured telemetry serialization and accumulation errors are safely caught and never alter execution outcome.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added regression tests across `test_telemetry.py`, `test_database.py`, `test_database_atomicity.py`, and `test_execution.py`.
  - `test_accumulator_validates_before_mutating_state`: failed with DID NOT RAISE, now passes.
  - `test_availability_tracked_per_measurement_instead_of_zero`: failed with `assert 0 is None`, now passes.
  - `test_context_invalidation_preserved_and_older_invocation_rejected`: failed with `assert 1000 is None`, now passes.
  - `test_observation_ordering_and_invocation_finalization`: failed with `assert 100 == 50`, now passes.
  - `test_retain_truthful_provenance`: failed with `assert 'reported' == 'estimated'`, now passes.
  - `test_merge_telemetry_validates_and_sanitizes_incoming`: failed with `assert -50 == 100`, now passes.
  - `test_merge_job_telemetry_validates_and_sanitizes_before_persistence`: failed with `AssertionError: assert 'telemetry' not in ...`, now passes.
  - `test_concurrent_terminal_and_telemetry_race`: passed concurrent race verification.
  - `test_telemetry_updated_dispatches_cumulative_totals_before_cache_fields`: failed with `assert 0 == 500`, now passes.
  - `test_unobserved_recovery_invocation_marks_totals_incomplete`: failed with `assert 'complete' == 'partial'`, now passes.
  - Full suite `cd server && uv run pytest`: 663 passed, 11 deselected in 119.59s.
- Root cause (bugfix only): 1) SQLite SELECT did not acquire write locks leading to race conditions; 2) unvalidated input mutated accumulator before model validation; 3) initial dict writes bypassed DB validation; 4) cumulative missing fields defaulted to 0; 5) unobserved recovery invocations were not tracked; 6) cache fields check preceded cumulative totals check; 7) merge resurrected invalidated context; 8) response replacement lacked timestamp ordering and invocation finalization; 9) snapshot hardcoded quality and refreshed timestamp.


## Fix 2

### Decisions made
- Persist a partial telemetry snapshot for every invocation, including invocations with no token observations, and account/finalize it in the invocation `finally` path so driver exceptions cannot omit unknown contributions.
- Reject context snapshots from older attempt/invocation identities and validate candidate measurements before advancing attribution or context state.
- Apply strict non-negative integer validation to all completed-attempt counters.
- Treat any terminal metadata `telemetry` key as validated input; invalid/non-dict values are ignored and cannot replace existing telemetry.
- Retain completed measurement availability, quality, source, and observation timestamp, including observed zero, when aggregating completed attempts.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added context identity/atomicity, completed counter validation, completed aggregate provenance/zero, and terminal null telemetry regressions. Full verification: `cd server && uv run pytest` passed (666 passed, 11 deselected).
- Root cause (bugfix only): missing invocation state was only recorded after normal return; context identity was updated before model construction; completed totals stored counters alone without measurement provenance; terminal merge distinguished only dict telemetry payloads.

