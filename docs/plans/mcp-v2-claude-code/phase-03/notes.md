<!-- ccg-shared-version: 11.0.6 -->

# Phase 3 Decision Notes

## Task 1

### Decisions made
- Replaced project FIFO reservation with a global ordered candidate scan. The scheduler reserves global, per-project reader/writer, and session-scope capacity synchronously before dispatch.
- Added startup-bound `max_project_readers`, per-job immutable admission metadata, and a synchronous readiness callback. Dependency-blocked candidates do not reserve capacity or establish writer barriers.
- A ready exclusive candidate is a barrier for later readers in its project; earlier readers may drain. Existing two-argument `enqueue` calls default to exclusive metadata and preserve the max-reader-1 FIFO behavior.
- Dispatch handles are generation-specific so completion of an old terminal notifier cannot release or signal a retried job's handles.

### Spec deviations
- none

### Tradeoffs accepted
- Scheduler operations rely on the existing single asyncio event-loop boundary; selection and reservation have no await between them.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_scheduler.py -q -k 'same_project_readers_with_distinct_scopes_overlap or identical_read_session_scopes_serialize or ready_writer_is_barrier or dependency_blocked_candidate'` -> 4 failed, 5 deselected. Regression calls failed because `ProjectScheduler` did not yet accept `max_project_readers` or `is_ready`.
- GREEN: `uv run --extra dev pytest tests/test_scheduler.py -q` -> 15 passed.
- Deterministic tests cover parallel distinct scopes, same-scope serialization, reader capacity, ready-writer barrier and waiting reasons, blocked-writer bypass and reevaluation, global capacity, exception recovery, close waiters, and stale retry dispatch cleanup.

## Task 2

### Decisions made
- `Runtime.submit(..., depends_on=...)` resolves and snapshots the execution plan, derives access class from that plan, and persists the class and links through the Phase 2 atomic API.
- Enqueued jobs carry saved access mode and session-scope metadata. A synchronous dependency-readiness callback uses persisted reverse links; submission and queue registration happen before notification awaits.
- Immediate unsuccessful dependencies create an already-cancelled job with causal error/event data. Runtime performs transitive cancellation synchronously before yielding, using reverse links only.
- Runtime closes any previously opened connection-context transaction before calling Phase 2's explicit-transaction creation API, preserving the former `create_job` connection-context behavior without changing Phase 2 files.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_execution.py -q -k 'runtime_submit_persists_dependencies or submit_with_failed_parent or dependency_waiting_consumes_no_worker'` -> 3 failed, 86 deselected. `Runtime.submit()` rejected the new `depends_on` argument.
- GREEN: final expanded selection `uv run --extra dev pytest tests/test_execution.py -q -k 'runtime_submit_persists_dependencies or submit_with_failed_parent or dependency_waiting_consumes_no_worker or runtime_submit_invalid_dependencies or multiple_parents_must_all_succeed or submission_access_class_includes_unsafe_fallback'` -> 6 passed, 101 deselected.
- The first post-implementation dependency-wait run had 2 passed and 1 failed because the test target's default target concurrency of 1 independently blocked the cross-project driver. The isolated fixture was set to target concurrency 2; the focused set then passed. This was fixture correction, not a scheduler change.
- Integration RED: existing recovery test `uv run --extra dev pytest tests/test_execution.py -q -k 'recovery_duplicate_prompt_only_suppression_when_history_adds_nothing'` failed with `sqlite3.OperationalError: cannot start a transaction within a transaction` when a caller-owned write transaction remained open. Runtime now commits any prior connection-context writes before calling Phase 2's atomic `BEGIN IMMEDIATE` API, preserving the previous create-job connection-context behavior. Same test -> 1 passed, 106 deselected. No Phase 2 file was changed; Runtime handles compatibility with an already-open caller transaction before invoking the atomic Phase 2 API.
- Coverage includes invalid unknown/duplicate/cross-project links without new rows; saved access class including an unsafe fallback beyond `max_attempts`; multi-parent readiness; no worker consumed by a blocked child; and immediate failed-parent cancellation.
- Compatibility RED: `uv run --extra dev pytest tests/test_execution.py -q -k 'recovery_duplicate_prompt_only_suppression_when_history_adds_nothing'` -> 1 failed, 106 deselected with `sqlite3.OperationalError: cannot start a transaction within a transaction`. Runtime compatibility change GREEN: same command -> 1 passed, 106 deselected. Phase 2 database implementation remains unchanged.

## Task 3

### Decisions made
- Terminal commits invoke a synchronous callback before notifier awaits. The callback commits transitive cancellation and then releases admission; normal completion waiters are released when that dispatch returns. Retry dispatch handles are distinct from completed attempts.
- Retry retains job ID and immutable links, checks unsuccessful parents before resetting state, and registers the queued retry with its persisted access/session metadata before notification awaits.
- Startup interrupts running rows and propagates interruption/already-terminal failure cancellations before any admission or notifier await. Queued jobs remain durable through shutdown; reserved-undispatched work is not started while closing.
- Target semaphore release now covers attempt persistence, streaming capability/recorder setup, invocation, and recorder cleanup failures. JobRunner task cancellation persists cancelled/interrupted state before re-raising and does not overwrite a terminal state if notification is cancelled.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED (retry): `uv run --extra dev pytest tests/test_execution.py -q -k 'retry_preserves_dependencies or retry_rejects_dependent or retrying_parent_does_not_revive or retry_is_not_lost or startup_cascades_interrupted'` -> 1 failed, 4 passed, 89 deselected. Retry of a dependent with an unsuccessful parent did not raise.
- RED (target lease): `uv run --extra dev pytest tests/test_execution.py -q -k 'target_semaphore_released_after_post_acquire_failures'` -> 4 failed, 94 deselected after correcting the fixture to persist its job row. Failures showed the semaphore remained acquired and active count leaked at post-acquisition failures.
- GREEN focused: `uv run --extra dev pytest tests/test_execution.py -q -k 'retry_preserves_dependencies or retry_rejects_dependent or retrying_parent_does_not_revive or retry_is_not_lost or startup_cascades_interrupted or target_semaphore_released_after_post_acquire_failures'` -> 9 passed, 98 deselected.
- RED (task cancellation): focused JobRunner cancellation test -> 1 failed, 106 deselected; database state remained `running` after the task was cancelled.
- GREEN (task cancellation): same command -> 1 passed, 106 deselected.
- Combined-capacity integration coverage confirms two project reader reservations, one target invocation at target concurrency 1, project-reader cap 2, and global worker cap 2 are simultaneously enforced.
- Deterministic coverage includes retry preserving links, waiting on unfinished dependencies, dependency-specific rejection, parent retry not reviving children, notifier/retry race, startup reconciliation, target setup/cleanup failures, callback exception survival, and shutdown durability.

## Task 4

### Decisions made
- Added only the approved `ActionResult.cancelled_dependents` field with an empty-list default.
- Added `Runtime.waiting_metadata(job_id)` returning derived `(waiting_on, waiting_reason)` only for queued jobs. Dependency reasons take priority; other blockers come from scheduler admission state.
- Queued cancellation returns the descendants actually cancelled in that call. Running cancellation returns no predicted descendants; the later terminal callback performs the cascade and releases their completion waiters.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_execution.py -q -k 'cancel_queued_parent_returns_transitive or action_result_cancellation_dependents or dependency_waiting_consumes_no_worker'` -> 3 failed, 97 deselected. Missing `ActionResult.cancelled_dependents` and `Runtime.waiting_metadata` were reported; queued cascades did not return dependent IDs.
- GREEN: `uv run --extra dev pytest tests/test_execution.py -q -k 'cancel_queued_parent_returns_transitive or action_result_cancellation_dependents or dependency_waiting_consumes_no_worker'` -> 3 passed, 104 deselected. An initial run had 1 failure because the test blocker was not released before awaiting its completion; the deterministic fixture now releases it before the final wait.
- Waiting-reason RED: `uv run --extra dev pytest tests/test_scheduler.py -q -k 'active_writer_reports_exclusive_and_reader_wait_reasons'` -> 1 failed, 14 deselected because an active writer was described as readers finishing. Corrected the reason to distinguish an existing exclusive job; same command -> 1 passed, 14 deselected.
- Coverage includes dependency waiting metadata, session/reader/global/writer waiting reasons, queued waiter release, diamond cancellation through three descendant levels, causal cancellation, and empty metadata for nonqueued jobs.

## Final verification
- `uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q` -> 137 passed in 26.07s.
- `uv run --extra dev pytest -q` -> 535 passed, 3 deselected in 33.71s.
- `git diff --check` -> passed, no output.

## B1 Recovery Fix

### Decisions made
- Added explicit `started` state to dispatch handles. A reserved dispatch whose worker has not begun `run_job` is still cancellable as queued; cancellation releases its reservation and waiter immediately.
- Stale ready-queue entries are skipped unless their exact dispatch object remains reserved and current for that job ID. A retry can therefore install a fresh dispatch generation without stale work executing or cleaning up its handles.
- Actual executing dispatches retain the existing event-based running-cancellation behavior.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED: `uv run --extra dev pytest tests/test_execution.py -q -k 'cancel_reserved_unstarted_parent_cascades_and_retry_uses_new_dispatch'` -> 1 failed, 108 deselected. The cancellation call returned `running` rather than `cancelled` for the queued-but-reserved parent.
- GREEN: same command -> 1 passed, 108 deselected. With the blocker notifier paused, parent and child cancelled immediately, the queued cancellation returned the actual child ID, waiter released, reservation was freed, retry queued, and only the new unset cancellation-event generation entered execution after the notifier released.
- Required Phase 3 suite: `uv run --extra dev pytest tests/test_scheduler.py tests/test_runtime.py tests/test_execution.py -q` -> 138 passed in 29.71s.
- Full suite: `uv run --extra dev pytest -q` -> 536 passed, 3 deselected in 32.63s.
- `git diff --check` -> passed, no output.
