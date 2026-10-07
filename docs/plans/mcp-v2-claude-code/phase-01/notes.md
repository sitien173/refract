<!-- ccg-shared-version: 11.0.6 -->

# Phase 1 Decision Notes

## Task 1

### Decisions made
- Set `_MCP_WAIT_TIMEOUT_S = 3600` and introduced `_MCP_HEARTBEAT_INTERVAL_S: float = 30.0` in `openmcp.server`.
- Replaced pre-wait and post-wait progress reports in `job_wait` with immediate progress reporting and periodic heartbeats during wait.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_job_wait_constants`, `test_mcp_exposes_direct_job_contract`, and `test_job_wait_bounds_public_timeout` failed when timeout was 300 and heartbeat interval constant was missing; passed after implementation.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Added `_progress_token_present` helper to read `ctx.request_context.meta` and identify presence of `progress_token` or `progressToken` while rejecting boolean values.
- Logged `progress_token_present` boolean in `_logged_request` for `job_wait` on start and finish logs without logging token value.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_job_wait_logs_progress_token_presence` failed when `progress_token_present` was absent; passed after adding logging in `_logged_request`.
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Used event-based deterministic synchronization in test mocks instead of sleep-based timing.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Coordinator owns daemon restart and live acceptance checks.

### Test evidence
- RED -> GREEN: Added deterministic test coverage in `tests/test_server.py` covering multiple heartbeat intervals before completion, immediate terminal return, non-terminal timeout, timeout capping at 3600, cancellation cleanup, and progress token presence/absence. All 32 server tests passed and full test suite passed (470 passed, 3 deselected).
- Root cause (bugfix only): - none
