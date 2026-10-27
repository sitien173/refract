# Phase 2: Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- Retry execution was not implemented; see clarification and continuation status.

### Tradeoffs accepted
- Avoided a wrapper that calls `_execute_attempt()` repeatedly, since it would release capacity/probe ownership and finalize health and turns per attempt, violating the approved contract.

### Assumptions
- none

### Follow-ups for human
- Refactor selected-target lifecycle so a policy sequence retains ownership and separates per-invocation records from final-only completion before implementing policy attempts.

### Test evidence
- Characterization before edits: `cd server && uv run --extra dev pytest tests/test_execution.py tests/test_telemetry.py tests/test_target_capacity.py tests/test_runtime.py` — 178 passed in 130.25s.
- No retry-policy RED/GREEN evidence; retry execution remains unimplemented.

## Task 2

### Decisions made
- Preserve existing cleanup/finalization flow; no unsafe attempt-loop refactor was made.

### Spec deviations
- Attempt observability, resource ownership across policy attempts, and final-only health behavior remain unchanged and policy retries are not implemented.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Implement shared selected-target lifecycle cleanup covering setup, ask-token issuance, recorder, and finalization failures before adding the policy loop.

### Test evidence
- Existing lifecycle characterization is included in the 178-pass baseline run above; no new retry lifecycle behavior was added.

## Task 3

### Decisions made
- Narrow rollover correction uses the greater of completed-attempt totals and completed measurement when no active usage exists, avoiding stale serialized aggregate underreporting.

### Spec deviations
- Retry acceptance/lifecycle regression suite was not added; only the telemetry rollover regression was implemented.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Complete execution, capacity, runtime retry acceptance coverage.

### Test evidence
- RED: `uv run --extra dev pytest -q tests/test_telemetry.py -k manual_to_automatic_rollover` failed: expected total input 250, got 150 (completed attempts already reported 250).
- GREEN: same targeted test passed as part of the final required command: 179 passed in 120.81s.
- Final command: `cd server && uv run --extra dev pytest tests/test_execution.py tests/test_telemetry.py tests/test_target_capacity.py tests/test_runtime.py` — 179 passed.
