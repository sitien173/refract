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

## Continuation 1: Task 1

### Decisions made
- Restructured `_execute_attempt` to run bounded same-target policy attempts using the immutable plan `RetryPolicy` snapshot.
- Evaluated eligibility: outcome `RETRYABLE`, not `context_overflow`, replay not blocked, and streaming supported with `StreamBridge`.
- Implemented policy rule matching: exact code matches or case-insensitive pattern substrings; empty rules allow all eligible transient failures.
- Maintained separate context-overflow recovery accounting and checked cancellation before each attempt.

### Spec deviations
- none

### Tradeoffs accepted
- Integrated the recovery loop directly into `_execute_attempt` so recovery state, session flags, and prompt replacement persist across attempts without restarting initial overflow.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_execution.py -k "test_retry_policy_matching or test_retry_policy_bounded or test_retry_policy_exclusions"` failed: `test_retry_policy_matching_code_or_pattern_and_empty_rules` failed (AssertionError: assert 'failed' == 'succeeded') and `test_retry_policy_bounded_attempts_and_budget_exhaustion` failed (AssertionError: assert 1 == 3).
- GREEN: passing with 3 tests in 4.69s after implementing bounded policy attempts, OR matching, and exclusions in `execution.py`.
- Full phase command passed 182 tests in 149.25s.

## Continuation 1: Task 2

### Decisions made
- Held target capacity permit and half-open probe across the entire selected-target sequence.
- Allocated unique `StreamRecorder` and ask token per policy attempt, revoking ask token and closing recorder in attempt cleanup.
- Finalized target health once at completion (`record_target_success` on success, `_update_target_health` on failure).
- Stored single successful turn in database, carrying over recovery session replacement.
- Rolled over telemetry accumulator once per attempt using `complete_attempt(attempt_number)`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- GREEN-only coverage (no documented prior RED): `test_retry_sequential_observability_streams_and_ask_tokens`, `test_retry_probe_and_capacity_held_and_final_only_health`, and `test_retry_telemetry_rollover_cumulative_consumption` verified attempt observability, continuous probe/capacity holding, and cumulative telemetry rollover (3 passed in 3.94s).

## Continuation 1: Task 3

### Decisions made
- Added deterministic fake-driver regressions for:
  - 10-attempt maximum bound for `retryAttempt = 9`
  - Replay blocked by tool activity after stream truncation
  - Replay blocked by unknown replay safety when structured streaming is unsupported
  - Session recovery continuity across transient policy failures to final success
  - Cancellation before retry invocation releasing capacity and probe
  - Injected cleanup failure handling without leaking capacity or probes
  - Concurrent probe blocking during retry sequences in `test_target_capacity.py`
  - Fresh policy budgets with cumulative attempt numbers on manual retries in `test_runtime.py`

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- GREEN-only coverage (no documented prior RED): 6 edge case tests in `test_execution.py` passed in 7.19s, `test_target_capacity.py` passed in 1.65s, `test_runtime.py` passed in 1.14s.
- Fresh full Phase 2 verification command: `cd server && uv run --extra dev pytest tests/test_execution.py tests/test_telemetry.py tests/test_target_capacity.py tests/test_runtime.py` passed 193 in 128.80s.
- `git diff --check` passed clean.

## FIX batch 1

### Decisions made
- Selected-target `execute()` owns post-acquisition cleanup: permit, active count, capacity accounting, and probe release are handled in its outer `finally`, including policy lookup and telemetry rollover failures.
- Allocate `_TargetAttempt` for every policy attempt; recovery phase/prompt/session progression remains in surrounding sequence locals.
- Ask issuance runs inside the attempt lifecycle and propagates failures before invoking the driver. Cleanup steps are attempted independently, preserving primary driver errors.
- Removed unused `_ExecutionContext.semaphore`; recovery event details accept heterogeneous values.

### Spec deviations
- none known; independent review remains pending.

### Tradeoffs accepted
- Use one acquired-target cleanup owner for probe release across exceptional and normal exits.

### Assumptions
- none

### Follow-ups for human
- Independent quality review and acceptance remain pending.

### Test evidence
- RED (intended reproductions): `uv run --extra dev pytest -q tests/test_execution.py -k 'retry_policy_lookup_failure or retry_ask_token_issue_failure or retry_driver_exception_does_not_reuse'` — lookup left probe `policy-lookup-fault` held; ask issuance failure did not raise; stale retryable result remained in attempt event after later invocation exception. Initial harness setup errors were corrected before this run.
- GREEN: same three tests — 3 passed, 135 deselected.
- Added injected faults for token revocation, recorder finalization, health update, and turn storage; accumulator rollover and policy lookup cleanup coverage. A first semaphore-map assertion was invalid because idle semaphores are removed; after correcting the assertion, focused set passed 8 tests, 135 deselected.
- Required phase command, final after cleanup nesting: `cd server && uv run --extra dev pytest tests/test_execution.py tests/test_telemetry.py tests/test_target_capacity.py tests/test_runtime.py` — 201 passed in 101.07s.
- Full server, final: `cd server && uv run --extra dev pytest` — 810 passed, 15 deselected in 113.83s.
- `git diff --check` passed. No configured LSP diagnostics runner was found in project configuration.

## Continuation 2: Evidence reconciliation

### Decisions made
- Correct historical labels for Continuation 1 Task 2 and Task 3: these are GREEN-only test evidence because no prior RED failure was documented. Preserve recorded RED failures for Continuation 1 Task 1 and FIX batch 1 as written.
- No product changes were necessary. Coordinator's clean checkpoint and independent validations are the final implementation evidence; independent quality review is a subsequent coordinator gate, not worker debt.

### Spec deviations
- none known from implementation evidence; independent review pending.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Coordinator to perform independent quality review.

### Test evidence
- Coordinator checkpoint at `868e7a9`: 201 focused tests passed; 810 server tests passed, 15 deselected; diff check passed.
- Final worker validation is listed under FIX batch 1: 201 focused and 810 full server tests pass; diff check passes.
