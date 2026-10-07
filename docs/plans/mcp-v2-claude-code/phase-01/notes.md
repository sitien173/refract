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

## Review Fix Cycle 1

### Decisions made
- Heartbeat reports now start consistently at progress 0 with `total=None`; each subsequent running heartbeat increments progress by 1 and omits the total.
- Presence logging reads raw `request_context.params["_meta"]["progressToken"]`, allowing exact `str` or `int` types and excluding `bool`; it does not infer presence from normalized `request_context.meta`.
- Inspected installed SDK extraction in `.venv/lib/python3.12/site-packages/mcp/server/runner.py`: `_extract_meta` validates raw params into normalized metadata. Boolean `true` normalizes to integer 1, fractional float 1.5 is rejected, and snake-case `progress_token` is accepted as normalized metadata. These normalized values cannot establish the exact raw wire token the SDK dispatches on.

### Test evidence
- RED (P1): `uv run --extra dev pytest tests/test_server.py -q -k 'heartbeat_loop_reports_progress_until_terminal or logs_progress_token_presence'` -> `test_job_wait_heartbeat_loop_reports_progress_until_terminal`: first mismatch `(0.0, 1.0, 'running') != (0.0, None, 'running')`.
- RED (P2): same command -> `test_job_wait_logs_progress_token_presence[wire_meta4-False]`: normalized boolean token logged as present; `test_job_wait_logs_progress_token_presence[wire_meta6-False]`: snake-case-only wire token logged as present. Overall: 3 failed, 7 passed.
- GREEN focused: same command -> 11 passed, 27 deselected.
- GREEN server: `uv run --extra dev pytest tests/test_server.py -q` -> 38 passed.
- GREEN full: `uv run --extra dev pytest -q` -> 476 passed, 3 deselected.

## Review Fix Cycle 2 — Logging Sink

### Decisions made
- JSON output preserves `progress_token_present` only when it is a direct log-record extra whose exact runtime type is bool. Every non-bool value still flows through the unchanged sensitive-key redactor.
- Text output appends only a genuine boolean `progress_token_present` to the existing context section. Other extra fields remain unrendered.
- Generic secret-key and message redaction behavior is unchanged.

### Test evidence
- RED: `uv run --extra dev pytest tests/test_logging.py -q -k 'progress_token_presence_formatter or progress_token_presence_boolean'` -> 4 failed, 1 passed, 9 deselected. JSON failed with `AssertionError: assert '[REDACTED]' is True` (also False); text failed because `progress_token_present=True/False` was absent from output.
- GREEN focused: same command -> 5 passed, 9 deselected.
- GREEN requested module checks: `uv run --extra dev pytest tests/test_server.py tests/test_logging.py -q` -> 52 passed.
- GREEN full: `uv run --extra dev pytest -q` -> 481 passed, 3 deselected.
- `git diff --check` -> passed.

## Task 4

### Decisions made
- Preserve only a genuine boolean under the exact progress_token_present field in each production formatter. The user approved the additional logging files.

### Spec deviations
- Phase 1's file set and verification command include logging_setup.py and test_logging.py under the approved scope extension.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED and GREEN evidence is recorded in Review Fix Cycle 2 above.
- The coordinator reran the original reproduction after the fix; JSON and text both exposed the boolean without a token value.
