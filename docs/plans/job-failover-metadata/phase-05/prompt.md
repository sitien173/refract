## User Request
Show the 3-state circuit breaker in the dashboard targets view, stop the profile editor and config mutation from writing the deprecated `max_attempts`, and update the coordinator plugin docs for the new MCP contract.

## Phase
Phase 5 of docs/plans/job-failover-metadata/PLAN.md: operators see breaker state, editors no longer write `max_attempts`, and coordinator docs describe `next_target`, `result.metadata`, and `targets_unavailable`. Read `docs/plans/job-failover-metadata/DESIGN.md` for breaker states and the public error contract before editing.

## Tasks
- task-1: Add `breaker_state: Literal["closed", "open", "half_open"]`, `cooldown_s: int`, and `probing: bool` to `TargetView`, computed in `TargetExecutor.views`. Render them in `Targets.jsx` so half-open and probing targets look distinct from open and closed ones, keeping the existing `circuit_open_until` handling.
- task-2: Remove the `max_attempts` input and its payload field from `ProfileEditor.jsx`. Stop `config_mutation.py` from writing `max_attempts`, while preserving an existing value on round-trip.
- task-3: Update `tool-contract.md` for the `job_submit` signature with `next_target`, the `job_wait` return with `result.metadata`, and an error table row for `targets_unavailable`. Add one rule to `SKILL.md` Gate 2: on a failed job, read `result.metadata.failure_kind`, then resubmit with `next_target`, resubmit with `fresh_session=true` for `context_overflow`, or report.

## Split
This phase runs as two sequential jobs. Each job does only its part and edits only its part's files plus notes.md and journal.md.
- Part A, server and docs: task-1 server side (`models.py`, `execution.py` `views`, `dashboard.py`, `test_dashboard.py`), task-2 server side (`config_mutation.py`, `test_config_mutation.py`), and task-3 (both plugin docs). Done when `cd /home/ngosi/projects/refract/server && uv run pytest -q` passes.
- Part B, UI: task-1 UI side (`Targets.jsx`, `Targets.test.jsx`) and task-2 UI side (`ProfileEditor.jsx`, `Profiles.test.jsx`). Part A is already in the working tree; consume its `TargetView` fields as they are. Do not edit any Part A file. Done when both suites pass.
- In notes.md, Part A appends `## Task 1`, `## Task 2`, `## Task 3`. Part B appends `## Task 1 (UI)` and `## Task 2 (UI)`. In journal.md, each part appends its own ERP block under `## Implementation Response`.

## Context
- `models.py` `TargetView` fields today: `id, model, backend, isolated, read_only, max_concurrency, active, healthy, circuit_open_until`.
- `execution.py` `TargetExecutor.views(targets)` reads `self.database.target_health(target_execution_key(target))`, which returns `circuit_open_until`, `cooldown_s`, and `probe_job_id`. Derive state from these fields: `probe_job_id` non-empty means `probing=True` and `breaker_state="half_open"`; `circuit_open_until` empty means `closed`; `circuit_open_until > now` means `open`; `circuit_open_until <= now` with no probe means `half_open`. `TargetExecutor._is_open(value, now, probe_job_id)` already defines "open for admission"; reuse it where it fits and do not change it. `views` currently calls `_is_open(open_until, now)` without the probe argument; leave `healthy` semantics unchanged.
- `runtime.py:697` is the only `views` caller. `dashboard.py` may need no change; edit it only if the targets payload requires it.
- `Targets.jsx` uses `isCircuitOpenUntil(row.circuit_open_until)` for filter counts, the status column (`healthy`, `unhealthy`, circuit-open), and the selected-target panel. Add the new states following those same patterns. Keep the attention filter counting open targets; decide whether half-open counts as attention and record the decision in notes.md.
- `ProfileEditor.jsx` references `max_attempts` at lines 47, 55, 126, 293, 650-651, and 680. `Profiles.test.jsx` fixtures contain `max_attempts`; fixtures may keep it as input data, but tests must assert saved payloads contain no `max_attempts`.
- `config_mutation.py`: `WorkflowPolicyData.max_attempts` is `int | None = None` in `models.py`; leave the model unchanged. `_apply_workflow_policy` decides expansion with `policy.max_attempts != len(targets)` and passes `max_attempts` to `ConfigurationMutationService.set_workflow_policy`, which writes the key on inline tables, sub-tables, and new inline policies. Required behavior: a new policy is written without `max_attempts`; an existing `max_attempts` in the file stays unchanged after a save; a payload with `timeout_s == 0` on a shorthand workflow stays shorthand. Reading profiles may still report `max_attempts` from the file.
- Phase 4 wire contract in `server/src/refract/server.py`: `_JOB_SUBMIT_DESCRIPTION`, `_JOB_WAIT_DESCRIPTION`, `_JOB_RETRY_DESCRIPTION`, `_INSTRUCTIONS`, `_ERROR_CODES`, and `_page_terminal_result`. `job_submit` takes `next_target: str = ""`. `job_wait` returns `{job:summary, result:{text, error, next_offset, metadata}}`. Metadata keys are `model_name, context_window_max, context_window_used, input_tokens, output_tokens, cached_input_tokens, duration_ms, failure_kind, retryable, next_target`. `failure_kind` values are `cancelled, circuit_open, replay_blocked, context_overflow, request_fatal, target_fatal, retryable`. An unknown or stale `next_target` returns `invalid_request` with next action "Resubmit without next_target.". `targets_unavailable` is `retryable=true` and adds integer `retry_after_s`; `job_submit` and `job_retry` can return it. Copy names and codes exactly from `server.py`.
- Doc rule for `SKILL.md`: the plugin docs keep target identity private. `next_target` is an opaque token, so the rule must not mention providers, models, or target IDs.

## Files
- `server/src/refract/models.py`
- `server/src/refract/execution.py`: `views` only
- `server/src/refract/dashboard.py`
- `server/src/refract/config_mutation.py`
- `server/web/src/screens/Targets.jsx`
- `server/web/src/screens/Targets.test.jsx`
- `server/web/src/components/ProfileEditor.jsx`
- `server/web/src/screens/Profiles.test.jsx`
- `server/tests/test_dashboard.py`
- `server/tests/test_config_mutation.py`
- `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- `plugin/skills/coordinating-multi-model-work/SKILL.md`
- `docs/plans/job-failover-metadata/phase-05/notes.md`
- `docs/plans/job-failover-metadata/phase-05/journal.md`

## Done When
- The dashboard targets API returns `breaker_state`, `cooldown_s`, and `probing`, and `Targets.jsx` shows half-open and probing targets distinctly from open and closed ones, with tests for each state.
- Profile editor save payloads contain no `max_attempts`, with a test asserting it.
- A config file with `max_attempts` round-trips through a profile save without losing or changing the value, and a new policy is written without `max_attempts`, with tests for both.
- `tool-contract.md` and `SKILL.md` match the Phase 4 names and codes in `server.py` exactly.
- No new `[daemon]` settings UI is added.
- `cd /home/ngosi/projects/refract/server/web && npx vitest run`
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
- In `execution.py`, change only `TargetExecutor.views`. Do not change breaker semantics, `_is_open`, selection, or probe claim and release paths.
- Do not change `server.py`, `runtime.py`, `planning.py`, or `database.py`.
- Test first. Append Task blocks to notes.md; append the ERP block under `## Implementation Response` in journal.md without overwriting its META.
- Run test suites serially, not in parallel.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
