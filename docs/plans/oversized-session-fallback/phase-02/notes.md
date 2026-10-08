<!-- ccg-shared-version: 11.0.1 -->

# Phase 2 - Decision Notes

## Task 1

### Decisions made
- Implemented `ScriptedRecoveryDrivers` recording `target_id`, `session_id`, `prompt`, and `emitted_tool_activity` for exact invocation assertions.
- Executed emitter in worker thread to emulate backend adapter runtime concurrency.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Phase 1 provides stable overflow and activity signals.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_recovery_resumed_overflow_followed_by_successful_reconstruction` initially failed with `AssertionError: assert 'failed' == 'succeeded'`; passed after implementing TargetExecutor internal recovery. All 10 deterministic recovery tests passing.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Added helper `_run_target_invocation` on `TargetExecutor` to manage per-invocation `StreamBridge` and stream draining into the attempt-level `StreamRecorder`.
- Maintained single semaphore acquisition and release, single `record_job_attempt`, and single recorder `attempt.finished` event across all internal invocations.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified via `test_recovery_resumed_overflow_followed_by_successful_reconstruction` and `test_recovery_reconstruction_overflow_followed_by_prompt_only_success` that stream recorder records single `attempt.finished` while multiple bridges drain sequentially.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Restricted recovery eligibility strictly to standard jobs with nonempty resumed `session_id`, `error_code == "context_overflow"`, no tool activity, no cancellation, and non-fatal outcome.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified via `test_fresh_job_bypasses_session_and_history_and_clears_prior_sessions` and `test_recovery_tool_activity_during_resumed_call`.
- Root cause (bugfix only): none

## Task 4

### Decisions made
- Ran reconstruction call using `_with_history(project.id, context_key, workflow, prompt)` with empty `session_id`.
- Conditioned prompt-only fallback on `reconstructed_prompt != prompt`, strictly bounding invocations to 2 when no history exists and 3 when history exists.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified via `test_recovery_reconstruction_overflow_followed_by_prompt_only_success` and `test_recovery_duplicate_prompt_only_suppression_when_history_adds_nothing`.
- Root cause (bugfix only): none

## Task 5

### Decisions made
- Set `replay_blocked` when any non-successful invocation observes `tool.started`, halting same-target recovery and cross-target failover immediately.
- Bypassed `_record_failure(target_key)` whenever `error_code == "context_overflow"` to maintain target health neutrality.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified via `test_recovery_tool_activity_during_resumed_call`, `test_recovery_tool_activity_during_reconstruction`, `test_recovery_ordinary_failure_followed_by_normal_failover`, and `test_recovery_all_bounded_calls_overflowing_before_normal_failover`.
- Root cause (bugfix only): none

## Task 6

### Decisions made
- Passed `clear_sessions=recovered` to `Database.append_turn` on successful job execution, saving the original prompt and replacement session atomically.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing `append_turn(clear_sessions=True)` remains sufficient.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified via `test_recovery_successful_replacement_resumed_by_next_job` and `test_recovery_original_prompt_and_completed_turn_stored_exactly_once`.
- Root cause (bugfix only): none

## Task 7

### Decisions made
- Emitted `target.context_overflow`, `target.session_recovery_started`, `target.session_recovery_finished`, and `target.session_replaced` events with strictly low-cardinality payloads (`workflow`, `target`, `phase`, `outcome`, `error_code`).
- Emitted `target.session_replaced` only after successful database turn persistence.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified exact event payloads and emission ordering in `test_recovery_resumed_overflow_followed_by_successful_reconstruction` and `test_recovery_reconstruction_overflow_followed_by_prompt_only_success`.
- Root cause (bugfix only): none

## Task 8

### Decisions made
- Added `test_append_turn_clear_sessions_clears_multiple_stale_and_preserves_unrelated` in `tests/test_database.py`.
- Verified routing attempt counting (`job.attempts`), target health circuits, failover, and replay blocking across all scenarios.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_append_turn_clear_sessions_clears_multiple_stale_and_preserves_unrelated` passed; all execution, database, smoke, and full test suites passed (424 passed).
- Root cause (bugfix only): none

## Fix: Bounded history returns original prompt when every turn is excluded

### Decisions made
- `_with_history` returns the original prompt unchanged when the byte budget excludes every stored turn, so the reconstructed prompt is byte-identical to the original.
- Added execution regressions for the reviewer-noted edge cases: all history excluded by bytes, recovery success with empty session ID, persistence rollback, `max_attempts == 1`, target-fatal recovery, request-fatal recovery, and job attempt counting.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `history_bytes` remains authoritative and is configured per daemon.

### Follow-ups for human
- none

### Test evidence
- Root cause: the `_with_history` loop appended nothing when the first turn exceeded `history_bytes`, then emitted a `Previous context:` wrapper around an empty body. The wrapper differed from the original prompt, so `reconstructed_prompt != prompt` triggered a redundant prompt-only call.
- RED: `test_with_history_returns_original_prompt_when_all_turns_exceed_history_bytes` failed (`assert 'Previous context:\n\n\n\nCurrent request:\n\nturn 2 prompt' == 'turn 2 prompt'`) and `test_recovery_all_history_excluded_by_bytes_avoids_duplicate_prompt_only` saw 3 invocations instead of 2.
- GREEN: both tests pass after returning the original prompt when no blocks are eligible.
- Focused edge coverage added and passing: `test_recovery_success_with_empty_session_clears_stale_without_replacement`, `test_recovery_persistence_rollback_preserves_stale_session`, `test_recovery_max_attempts_one_stays_on_selected_target`, `test_recovery_target_fatal_uses_normal_health_and_failover`, `test_recovery_request_fatal_stops_recovery_and_failover`, `test_recovery_internal_calls_count_one_selected_target_attempt`.
- Rerun: `uv run pytest tests/test_execution.py -k 'overflow or recovery or fresh or history or retry'` -> 31 passed; `uv run pytest tests/test_database.py -k 'append_turn or session'` -> 6 passed; `uv run pytest tests/test_smoke.py -k 'pi'` -> 27 passed; `uv run pytest` -> 432 passed; `uv build` -> succeeded.
