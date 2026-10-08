<!-- ccg-shared-version: 11.0.4 -->

# Phase 2: Decision Notes

Append one task block per worker-contract.md, preserving decisions, deviations, assumptions, follow-ups, and RED to GREEN evidence.

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_notifications.py -q` -> 5 failed, 4 passed (`assert False is True`)
  - GREEN: `uv run pytest tests/test_notifications.py -q` -> `9 passed in 0.23s`
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications" -q` -> 4 failed, 2 passed (`assert 0 == 1`)
  - GREEN: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications" -q` -> `6 passed, 77 deselected in 0.45s`
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_notifications.py -q` -> 5 failed, 4 passed (asserted Notify construction, title, message format, empty target fallback, sensitive content omission, and boolean conversion)
  - GREEN: `uv run pytest tests/test_notifications.py -q` -> `9 passed in 0.23s`
- Root cause (bugfix only): - none

## Task 4

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications" -q` -> 4 failed, 2 passed (asserted succeeded, failed, queued cancel, and startup recovery calls, non-terminal omission, failure isolation, and live catalog toggle)
  - GREEN: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications" -q` -> `6 passed, 77 deselected in 0.45s`
- Root cause (bugfix only): - none

## Task 5

### Decisions made
- Snapshot JobView before first await in Runtime._notify_job_resource when notifications enabled; defer lookup exceptions to warning-only log after MCP publication.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_execution.py -k "test_concurrent_retry_preserves_terminal_notification" -q` -> 1 failed, 83 deselected (`AssertionError: assert 0 == 1`)
  - GREEN: `uv run pytest tests/test_execution.py -k "test_concurrent_retry_preserves_terminal_notification" -q` -> `1 passed, 85 deselected in 0.19s`
- Root cause (bugfix only): In `Runtime._notify_job_resource`, post-await job lookup read the reset state ("queued") when a concurrent retry ran during MCP publication await, causing terminal notification delivery to be skipped. Resolved by snapshotting the persisted `JobView` before the first await when notifications are enabled, deferring any lookup exception to a warning log after MCP publish completes, and using the captured snapshot for desktop notification dispatch.
- Warning characterization: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications_failure_isolation" -q` -> `1 passed, 82 deselected in 0.43s` (asserted event `job.desktop_notification_failed` and `job_id` for both false return and exception).
- Targeted control flow tests: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications_snapshot_lookup_failure_warning_only or test_terminal_desktop_notifications_disabled_does_not_lookup_job" -q` -> `2 passed, 84 deselected in 0.38s`.

## Task 6

### Decisions made
- Passed explicit exc_info=(type(lookup_error), lookup_error, lookup_error.__traceback__) in Runtime._notify_job_resource for deferred lookup warnings outside except handler.
- Kept scheduler unstarted in concurrent retry regression test to prevent premature job execution.
- Added try/finally with await runtime.close() to snapshot lookup failure and disabled no-lookup tests.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications_snapshot_lookup_failure_warning_only" -q` -> 1 failed, 85 deselected (`AssertionError: assert None is RuntimeError` from `NoneType: None`)
  - GREEN: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications_snapshot_lookup_failure_warning_only" -q` -> `1 passed, 85 deselected in 0.22s`
- Root cause (bugfix only): `log.warning(..., exc_info=True)` outside an active exception handler evaluates `sys.exc_info()` to `(None, None, None)`. Resolved by passing the captured `lookup_error` triplet `(type(lookup_error), lookup_error, lookup_error.__traceback__)` as `exc_info`.
- Concurrency regression runs:
  - Run 1: `uv run pytest tests/test_execution.py -k "test_concurrent_retry_preserves_terminal_notification" -q` -> `1 passed in 0.23s`
  - Run 2: `uv run pytest tests/test_execution.py -k "test_concurrent_retry_preserves_terminal_notification" -q` -> `1 passed in 0.19s`
  - Run 3: `uv run pytest tests/test_execution.py -k "test_concurrent_retry_preserves_terminal_notification" -q` -> `1 passed in 0.18s`
- Control-flow tests: `uv run pytest tests/test_execution.py -k "test_terminal_desktop_notifications_snapshot_lookup_failure_warning_only or test_terminal_desktop_notifications_disabled_does_not_lookup_job" -q` -> `2 passed in 0.18s`
