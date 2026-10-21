## User Request
Expose job result metadata and a live opaque `next_target` routing token over MCP, accept `next_target` on `job_submit`, and fail `job_submit` and `job_retry` fast with a new `targets_unavailable` error when every candidate target is open.

## Phase
Phase 4 of docs/plans/job-failover-metadata/PLAN.md: the MCP client can read job metadata and route a follow-up job to the next healthy target without seeing target identity. Read `docs/plans/job-failover-metadata/DESIGN.md` sections "Submit", "Token", "Result", "`failure_kind` and `retryable`", and "Public errors" before editing.

## Tasks
- task-1: In `planning.py`, add a token function: `"nt_"` + first 16 hex chars of `sha256` over `config_revision`, `project_id`, `profile`, `workflow`, and `target_execution_key(target)`, joined with an unambiguous separator. Add a resolver that maps a token to one candidate `TargetConfig` of a resolved plan, or `None`.
- task-2: `Runtime.submit` and the `job_submit` tool gain optional `next_target: str = ""`. A match pins the stored plan to that one target, using `dataclasses.replace` on `plan.selection` and `plan.targets`. No match raises `invalid_request` with next action "Resubmit without next_target.". Then run a breaker pre-check over the plan's candidates; if all are open, raise `targets_unavailable`, `retryable=True`, with `retry_after_s` before any database insert. Apply the same pre-check in `Runtime.retry` against the job's stored plan, before `reset_retry`.
- task-3: Register `targets_unavailable` in `_ERROR_CODES`. Carry `retry_after_s` from `OrchestrationError` through `RefractError` into the public payload. `_valid_refract_error` accepts `retry_after_s` as an int only when `code == "targets_unavailable"`; every other code still requires exactly `_ERROR_FIELDS`.
- task-4: `job_wait` adds `result.metadata` to every terminal page. For failed and cancelled jobs, compute `next_target` live at wait time and recompute `retryable` from it. Update `_JOB_SUBMIT_DESCRIPTION`, `_JOB_WAIT_DESCRIPTION`, `_JOB_RETRY_DESCRIPTION`, and `_INSTRUCTIONS`.

## Context
- `planning.py`: `ExecutionPlan(profile, workflow, selection, targets)`, `resolve_execution_plan(workflow, config, profile)`, `parse_execution_plan`, `target_execution_key(target)`. `TargetSelection` is a frozen dataclass in `config.py` with `targets`, `max_attempts`, `timeout_s`.
- `runtime.py` `submit` loads `catalog` under `self.mutations.lock`; `catalog.config_revision` is the current revision. `retry` validates state and dependencies, then calls `self.database.reset_retry`. `self.target_executor` is the `TargetExecutor`. Pass `retry_after_s` by adding an optional `retry_after_s: int | None = None` to `OrchestrationError`.
- Breaker state in `execution.py`: `self.database.target_health(target_execution_key(target))` returns `circuit_open_until` and `probe_job_id`. `TargetExecutor._is_open(open_until, now, probe_job_id)` defines open. Half-open, where `circuit_open_until <= now` and no probe, is admissible and not open. Reuse `_is_open`; do not duplicate its logic. Config keys `breaker_base_cooldown_s` live on the daemon config.
- `retry_after_s`: integer seconds until the earliest `circuit_open_until` among candidates, rounded up, minimum 1. When a candidate is open only because a probe is in flight, its estimate is `breaker_base_cooldown_s`. Take the minimum across candidates.
- `jobs.target_id` holds the failed target's config `id`, or `''` when the job failed `circuit_open` before any driver call. `JobView.result.metadata` holds the stored ten-key dict from Phase 3. Its stored `next_target` is null and its stored `retryable` is False for `retryable`, `target_fatal`, `circuit_open`, and `cancelled`.
- `next_target` at wait time: resolve the job's profile and workflow against the project's current catalog, the same way `submit` does. Find the failed `target_id` in the candidate order and scan later candidates for the first non-open one. When `target_id` is empty or not in the current candidates, scan from the start. Return its token, else `null`. On config or profile resolution failure, return `null`. For failure kinds `retryable`, `target_fatal`, `circuit_open`, and `cancelled`, `retryable` = `next_target is not None`. Leave `context_overflow`, `request_fatal`, and `replay_blocked` values as stored. Succeeded jobs keep `next_target` and `retryable` null. Jobs with empty stored metadata return all ten keys null. Never write `next_target` to the database.
- `server.py`: `_page_terminal_result` builds each terminal page and shrinks text to fit `_fits_response`; metadata must be in every page and inside the size check. `_public_data` and `_FORBIDDEN_OUTPUT_KEYS` must stay unchanged; `config_revision` is a forbidden key, so the token hashes it but never exposes it.
- `models.py` may need a field for metadata or the new `SubmissionResult` input; change it only if required. `JobSummary` field set is unchanged.

## Files
- `server/src/refract/planning.py`
- `server/src/refract/runtime.py`
- `server/src/refract/server.py`
- `server/src/refract/models.py`
- `server/tests/test_runtime.py`
- `server/tests/test_server.py`
- `server/tests/test_execution.py`: only the three tests named in Coordinator clarification 1
- `docs/plans/job-failover-metadata/phase-04/notes.md`
- `docs/plans/job-failover-metadata/phase-04/journal.md`

## Done When
- A failed job's `job_wait` returns a non-null `next_target` when a second healthy target exists, and `null` when none does.
- Submitting with that token runs the job on the second target.
- A token from another profile, or from before a config reload, returns `invalid_request`.
- With all targets open, `job_submit` returns `targets_unavailable`, `retryable=true`, and an integer `retry_after_s`, and the job table row count is unchanged.
- `job_retry` returns `targets_unavailable` under the same condition.
- Every terminal page includes `result.metadata`, and each serialized response stays under 9,000 UTF-8 bytes.
- Serialized MCP payloads contain no `target_id`, `backend`, or `model` key.
- `cd /home/ngosi/projects/refract/server && uv run pytest -q tests/test_runtime.py tests/test_server.py`
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
- Do not change `execution.py`, `database.py`, breaker semantics, or probe claim and release paths.
- Do not change `_public_data`, `_FORBIDDEN_OUTPUT_KEYS`, or the `JobSummary` field set.
- Do not edit `plugin/` docs; Phase 5 owns them.
- Test first. Append Task blocks to notes.md; append the ERP block under `## Implementation Response` in journal.md without overwriting its META.
- Run test suites serially, not in parallel.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
