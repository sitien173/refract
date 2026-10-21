<!-- refract-shared-version: 1.2.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Replaced the attempt loop with a single selection and invocation; retained same-target context-overflow repair, with transcript attempt IDs fixed at 1.
- `_select_target` no longer takes an attempted-target set. It retains first-available-capacity then first-admissible fallback behavior and Phase 2 probe claims.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing `TargetSelection.max_attempts` remains only for stored plan compatibility and is not consulted by dispatch.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: the added retryable-failure regression was written before implementation; it exposed the missing `JobResult.metadata` field on the initial run. Its assertions cover one target invocation and persisted single-run metadata after implementation.
- Updated legacy fallback/attempt-label assertions to match a single selected target while preserving overflow-repair and stream behavior. Execution/runtime/scheduler/smoke suite: 209 passed.
- `! grep -n "random\\|retry_scheduled" src/refract/execution.py` passed.

## Task 2

### Decisions made
- Dispatch with no admissible target returns `DriverResult(outcome="REQUEST_FATAL", error_code="circuit_open")`. `REQUEST_FATAL` is excluded from breaker counting; metadata marks this as `circuit_open`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Phase 4 will decide whether retryable is true using live `next_target`, so stored `retryable` remains false.

### Follow-ups for human
- none

### Test evidence
- `test_all_open_targets_fail_dispatch_without_counting_or_invoking_driver` confirms no backend call, unchanged failure counts, and the `circuit_open` metadata reason.

## Task 3

### Decisions made
- Added `TargetExecutionResult.metadata` with every schema key. Usage values are copied from `DriverResult.usage`; absent usage remains null. Configured model is used when the stream reports no model.
- Failure classification follows the specified precedence. Duration is an integer for a driver run and null when no target ran. `next_target` remains null pending Phase 4.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- A non-empty configured model is suitable as the public model fallback.

### Follow-ups for human
- none

### Test evidence
- `test_retryable_failure_runs_one_target_and_persists_result_metadata` verifies one driver call, all metadata keys, model fallback, usage propagation, integer duration, retryable failure classification, and persistence through `JobView.result`.
- Full suite: 564 passed, 3 deselected.

## Fix 1

### Decisions made
- `TargetExecutor` attaches complete metadata to raised exceptions. Driver exceptions map to `request_fatal`; cancellation maps to `cancelled`. Metadata uses the selected target's configured model and elapsed run duration when invocation began.
- `JobRunner` persists attached exception metadata and supplies a complete schema-shaped fallback when execution terminates before metadata is returned, ensuring retries replace old JSON.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `BaseException` instances permit an internal metadata attribute; attachment is guarded for unusual immutable exceptions.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: driver-exception and task-cancellation tests initially received empty metadata; retry test retained the previous run's `retryable` metadata rather than replacing it with `request_fatal`. All three pass after exception metadata propagation and JobRunner fallback persistence.
- Driver-exception metadata includes all ten keys, configured model fallback, and integer duration; cancellation during driver execution includes all keys, `cancelled`, model fallback, and duration; retry overwrites prior run usage/model metadata.
- Targeted suite: 210 passed. Full suite: 565 passed, 3 deselected. Required grep check passed.

## Task 4

### Decisions made
- Added optional metadata arguments to both terminal database writers. `None` preserves the existing JSON column value/default; provided metadata is JSON-serialized. `JobResult.metadata` defaults to an empty dictionary for historical rows.
- JobRunner passes execution metadata on success and on terminal failure/cancellation following an execution result.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Historical metadata JSON that is absent, malformed, or not an object safely yields `{}` in the public `JobResult`.

### Follow-ups for human
- Phase 4 will add live `next_target` calculation without changing `JobSummary`.

### Test evidence
- Existing legacy schema/runtime tests and the new failed-job metadata regression pass with persisted metadata.
- Serial verification: `uv run pytest -q tests/test_execution.py tests/test_runtime.py tests/test_scheduler.py tests/test_smoke.py` — 209 passed; `uv run pytest -q` — 564 passed, 3 deselected.

### Rewritten tests
- `test_retries_reuse_targets_after_each_failover_pass` -> `test_transient_failure_does_not_schedule_another_attempt`: one transient failure ends after one selection.
- `test_cancellation_interrupts_retry_backoff` -> `test_transient_failure_returns_without_retry_backoff`: no backoff exists; a transient failure completes once.
- `test_retry_attempts_recompile_argv_per_backend`: now asserts only the first target is invoked once.
- `test_fresh_job_failover_preserves_freshness` -> `test_fresh_job_failure_preserves_freshness_without_fallback`: failed fresh run does not silently switch targets or alter existing sessions.
- `test_failed_attempts_retain_attempt_labels` -> `test_single_failed_attempt_transcript_uses_attempt_one`: records one failure transcript with attempt 1.
- `test_attempt_finished_does_not_reuse_prior_attempt_on_exception` -> `test_attempt_finished_records_driver_exception_as_request_failure`: validates one-run exception recording.
- `test_execution_retries_across_runtime_reload` -> `test_single_failed_execution_metadata_survives_runtime_reload`: persists one failed run's transcript and metadata.
- `test_recovery_ordinary_failure_followed_by_normal_failover` -> `test_recovery_ordinary_failure_stops_without_cross_target_fallback`: keeps overflow repair on primary but does not dispatch secondary after ordinary failure.
- `test_recovery_all_bounded_calls_overflowing_before_normal_failover` -> `test_recovery_overflow_repair_stays_on_selected_target_without_fallback`: verifies bounded overflow repair remains same-target and has no fallback.
- `test_recovery_target_fatal_uses_normal_health_and_failover` -> `test_recovery_target_fatal_opens_breaker_without_cross_target_fallback`: immediate target-fatal opening prevents second-target dispatch.
- `test_recovery_internal_calls_count_one_selected_target_attempt` -> `test_recovery_internal_calls_count_one_selected_target_attempt_without_fallback`: same-target repair invocations count as one selected target attempt.
