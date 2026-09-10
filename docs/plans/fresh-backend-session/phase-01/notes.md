# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Guarded fresh_session column addition with table column check.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: pytest tests/test_server.py tests/test_database.py failed with 8 errors then passed 35 tests.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Added clear_context_sessions to database facade.
- TargetExecutor reads fresh_session to bypass session and history.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: test_fresh_job_bypasses_session_and_history_and_clears_prior_sessions failed asserting empty session, then passed.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Documented fresh_session in README tool table and payload.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Worker reported RED -> GREEN coverage for failover, retry, restart, and history.
- Root cause (bugfix only): none

## Coordinator verification

- `uv run pytest tests/test_database.py tests/test_execution.py tests/test_server.py`: 67 passed.
- `uv run pytest tests/test_execution.py -k fresh`: 7 passed.
- `uv run pytest`: 308 passed, 3 deselected.
- `git diff --check`: passed.
- `uv build`: passed.
- `uv run ruff check src/openmcp tests`: unavailable because `ruff` is not a project dependency.
