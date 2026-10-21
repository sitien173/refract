## User Request
Implement plan `job-failover-metadata` (client-routed failover, job result metadata, 3-state circuit breaker). This is Phase 3 of 5. Phase 1 (backend usage parsing) and Phase 2 (3-state breaker, config keys, schema v13) are complete.

## Phase
Each job makes exactly one target selection, never silently falls back to another target, and stores `jobs.result_metadata_json` matching the DESIGN.md `result.metadata` schema.

## Tasks
- task-1: In `TargetExecutor.execute` (`execution.py`), remove the `for attempt in range(plan.selection.max_attempts)` loop, the `attempted` set and its clearing, the `import random`, and the backoff and `target.retry_scheduled` code. Keep context-overflow repair on the same target, the recorder, semaphores and `_target_active` accounting, session handling, probe release and breaker accounting from Phase 2, and the existing events. `target.attempt_started` and `target.attempt_finished` are emitted once per job. Event payloads that carry `attempt` use `1`. Drop the `attempted` parameter from `_select_target` and update its callers. Selection stays: first non-open target with free capacity, else first non-open target, with half-open admission through the Phase 2 probe claim.
- task-2: When no target is admissible at dispatch, return a failed result with `error_code="circuit_open"` without calling the driver. It replaces today's `DriverResult("TARGET_FATAL", "", "", "No healthy target", "no_target")` default. It is not counted by the breaker. Choose a `DriverResult.outcome` that the breaker counting already treats as not counted, and record the choice in notes.md.
- task-3: Build metadata in `execute()` and return it on `TargetExecutionResult` as a new `metadata: dict[str, Any]` field. Keys, all present on every result:
  `model_name`, `context_window_max`, `context_window_used`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `duration_ms`, `failure_kind`, `retryable`, `next_target`.
  - Usage keys come from `DriverResult.usage` (Phase 1). Unreported keys are `None`.
  - `model_name` falls back to the target's configured `model` when the stream reports none.
  - `duration_ms` is the integer wall clock of the target run, including overflow repair. `None` when no driver ran.
  - `next_target` is always `None` here; Phase 4 computes it at `job_wait` time.
  - On success, `failure_kind` and `retryable` are `None`.
  - On failure, `failure_kind` is chosen by the first matching rule, in this order: `cancelled` (outcome `CANCELLED`), `circuit_open` (task-2 path), `replay_blocked` (tools ran and outcome is not `SUCCESS`), `context_overflow` (final `error_code == "context_overflow"`), `request_fatal`, `target_fatal`, `retryable`.
  - `retryable`: `context_overflow` is `True`; `request_fatal` and `replay_blocked` are `False`; `retryable`, `target_fatal`, `circuit_open`, and `cancelled` are `False` here, because their value is `True` only when `next_target` is non-null and `next_target` is `None` at storage time. Phase 4 recomputes it at wait time.
- task-4: Persist metadata. Add an optional `metadata: dict[str, Any] | None = None` keyword to `Database.finish_job` and `Database.finish_fresh_job_success` that writes `jobs.result_metadata_json` as JSON; omitted keeps the column default. Pass the execution metadata from every `finish_job`/`finish_fresh_job_success` call in `execution.py` that follows a target execution. Add `metadata: dict[str, Any] = Field(default_factory=dict)` to `JobResult` in `models.py` and populate it from `result_metadata_json` where `JobView` is built (`database.py` ~line 822). `JobSummary` is unchanged.

## Context
- Design: `docs/plans/job-failover-metadata/DESIGN.md`, sections "Dispatch", "Result", "`result.metadata` schema", "`failure_kind` and `retryable`", "Behavior change".
- Today: `execution.py` `execute()` starts ~line 52 with the attempt loop at ~line 56; retry/backoff at ~lines 352-356; `_select_target(target_ids, plan, attempted, job_id)` at ~line 424; `finish_job` / `finish_fresh_job_success` calls at ~lines 569-614. `database.py` `finish_job` at ~line 737, `finish_fresh_job_success` at ~line 747, `result_metadata_json` column exists since v13. `models.py` `JobResult` at line 23 has `text` and `error`.
- `TargetSelection.max_attempts` stays on the model so stored `execution_plan_json` keeps loading; `execute()` no longer reads it.
- Behavior change: a transient failure now ends the job. Existing tests that assert cross-target fallback, a second driver call, `attempts == 2`, or `target.retry_scheduled` must be rewritten to the single-selection behavior, not deleted without replacement. List every rewritten test by name in the ERP NOTES.
- `server.py` is Phase 4 scope. If a `server.py` test fails only because `JobResult` gained `metadata`, stop and report it under CLARIFICATIONS NEEDED with `NEXT: BLOCKED`; do not edit `server.py`.

## Files
- `server/src/refract/execution.py`
- `server/src/refract/database.py`, limited to `finish_job`, `finish_fresh_job_success`, and `JobView` construction
- `server/src/refract/models.py`, limited to `JobResult`
- `server/tests/test_execution.py`
- `server/tests/test_runtime.py`
- `server/tests/test_scheduler.py`, only where it asserts fallback
- `server/tests/test_smoke.py`, only where it asserts fallback
- `docs/plans/job-failover-metadata/phase-03/notes.md` and `journal.md`

## Done When
- With two targets and the first returning `RETRYABLE`, the driver is called once and the job fails with `failure_kind="retryable"`.
- Context-overflow repair still succeeds on the same target.
- With every target open at dispatch, the driver is never called and `failure_kind="circuit_open"`, and `consecutive_failures` is unchanged.
- `job.result.metadata` holds every schema key; unreported keys are `None`; `model_name` falls back to the configured model; `duration_ms` is an int after a driver run.
- Semaphore and `_target_active` return to their prior values on every exit path, including cancellation and driver exceptions.
- No test still asserts cross-target fallback; each rewritten test is listed.
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_execution.py tests/test_runtime.py tests/test_scheduler.py tests/test_smoke.py`
- `cd /home/ngosi/projects/refract/server && ! grep -n "random\|retry_scheduled" src/refract/execution.py`
- `cd /home/ngosi/projects/refract/server && uv run pytest -q`

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

- Edit only the files listed above. Do not touch any other file under `docs/plans/`.
- No Git operations: no commit, reset, restore, stash, or clean.
- Do not read or modify `~/.refract` or any secret-bearing file.
- Do not change Phase 2 breaker semantics, probe claim SQL, or probe release paths except where removing the loop requires moving them; every claimed probe is still released or resolved on every exit path.
- Do not change `JobSummary` or any MCP tool description.
- Test first. Append Task blocks to notes.md; append the ERP block under `## Implementation Response` in journal.md without overwriting its META.
- Run test suites serially, not in parallel.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
