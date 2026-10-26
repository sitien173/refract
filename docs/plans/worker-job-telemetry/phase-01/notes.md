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
