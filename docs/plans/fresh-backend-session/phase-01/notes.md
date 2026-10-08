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

- Initial implementation: `uv run pytest tests/test_database.py tests/test_execution.py tests/test_server.py`: 67 passed.
- Initial implementation: `uv run pytest`: 308 passed, 3 deselected.
- First review repair: focused suite: 70 passed. Full suite: 311 passed, 3 deselected.
- Atomic-finalization repair: focused suite: 71 passed. Full suite: 312 passed, 3 deselected.
- `git diff --check`: passed before every implementation commit.
- `uv build`: passed after every implementation revision.
- Final review: PASS. It verified rollback when the succeeded-state update or success-event insert fails.
- `uv run ruff check src/openmcp tests`: unavailable because `ruff` is not a project dependency.
