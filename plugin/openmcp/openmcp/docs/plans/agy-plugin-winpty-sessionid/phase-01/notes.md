<!-- ccg-shared-version: 5.3.1 -->

# Phase 01 — Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- Removed recursion-avoidance plugin disabling as requested.

### Assumptions
- Existing top-level AGENTS references to the host plugin stay valid.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: removal task. `uv run --extra dev pytest -q tests/test_smoke.py` passed after deleting stale tests.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Tested the new path through `execute`.

### Spec deviations
- none

### Tradeoffs accepted
- Removed stale history and conversation-file fallbacks as requested.

### Assumptions
- Only exact `Created` and `Streaming` log lines are valid.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run --extra dev pytest -q tests/test_smoke.py::test_agy_uses_input_session_id_when_log_has_no_conversation_id` failed before the backend change, then the Task 3 focused tests passed.
- Root cause (bugfix only): old fallback chain preferred stale history over the caller-provided session id.

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- Removed Windows ConPTY support as requested.

### Assumptions
- The log-file path is valid on Windows too.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: removal task. `uv run --extra dev pytest -q tests/test_smoke.py` passed after deleting stale tests.
- Root cause (bugfix only): none
