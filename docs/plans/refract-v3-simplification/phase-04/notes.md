# Phase 4 notes

Status: complete.

Execution mode: direct, per owner on 2026-11-04. No coordinator, no Refract jobs, no review gates.

## Baseline

At `7988f55a`:
- PYTEST: 1126 passed, 15 deselected.
- PLUGIN: session-start, contracts, and stats tests passed.
- LINES: 12009.

## Owner decisions

- 2026-11-04: the one schema migration also renames `context_key` to `session` and `fresh_session` to `fresh` with SQLite `RENAME COLUMN`, so the verification grep holds as written. Data is kept. This is not strictly additive, which PLAN.md Phase 4 boundaries otherwise require.
- 2026-11-04: `job.project` is the canonical Git root path.

## Step plan

- 4A: schema 17 and renames. 4B: runtime. 4C: six MCP tools. 4D: ask fixes. 4E: plugin and docs. One commit each.

4A design, before code:
- `_SCHEMA_VERSION = 17`. Migration 16 to 17 in one transaction: `jobs` rename `context_key` to `session` and `fresh_session` to `fresh`, add `retry_of TEXT NOT NULL DEFAULT ''`; `context_sessions` and `context_turns` rename `context_key` to `session`; create `sessions(project_id REFERENCES projects ON DELETE CASCADE, session, workflow, sticky_target, updated_at, PRIMARY KEY(project_id, session, workflow))`. SQLite 3.46.1 rewrites the `context_turns_stream_idx` columns on rename.
- Schema 15 opens through the existing 15 to 16 step, then 16 to 17.
- Old column names live only in split-literal constants, the pattern `config.py` already uses for removed keys, so the verification grep holds.
- `_validate_schema` picks column names by version: old names for 15 and 16, new names plus `retry_of` and the `sessions` table for 17.
- Python renames across `server/src`: `context_key` to `session`, `fresh_session` to `fresh`, and in `execution.py` `session_context_key` to `scoped_session`. `JobView`, `JobSummary`, `DashboardJob` field `context_key` becomes `session`.

## Step 4A: schema 17 and session renames

RED:
- `test_schema16_migrates_to_17_renaming_session_columns` and `test_schema15_migrates_to_17` in `tests/test_database.py`. Both failed with `assert 16 == 17` before the change.

GREEN:
- PYTEST: 1129 passed, 15 deselected. Baseline was 1126; 2 new tests and 1 new parametrized case for a stamped empty schema-17 file.
- PLUGIN: pass. LINES: 12045. Ruff F: no new findings against HEAD.

Changes:
- `database.py`: `_SCHEMA_VERSION = 17`. New `_migrate_schema16` runs in one transaction: renames the session column in `jobs`, `context_sessions` and `context_turns` to `session`, renames the fresh flag in `jobs` to `fresh`, adds `jobs.retry_of`, creates `sessions`. Schema 15 runs the existing 15 to 16 step first. New databases get `retry_of` and `sessions` directly.
- `_validate_schema` accepts 15, 16 and 17 and picks column names by version. Old names live only in the split-literal constants `_LEGACY_SESSION` and `_LEGACY_FRESH`.
- Python renames in `database.py`, `execution.py`, `runtime.py`, `models.py`, `notifications.py`: the session parameter and fields are now `session`, the fresh flag is `fresh`, and `execution.py` uses `scoped_session` for the environment-scoped key. `JobView`, `JobSummary` and `DashboardJob` expose `session`.
- Tests renamed to match. Schema-15 fixture SQL keeps the old names on purpose.

Deviations:
- `server.py` keeps the v2 MCP parameter names `context_key` and `fresh_session` on `job_submit` and in the MCP instructions. They map to the new runtime names. Step 4C replaces the whole tool surface, so renaming them twice would be wasted work. The `JobSummary` output field is already `session`.
- Unsupported-schema messages now name schemas 15, 16 and 17.

Debt:
- The `sessions` table exists but nothing reads or writes it yet. Step 4B adds sticky targets.

## Step 4B: runtime Git root, sticky target, retry as new job, result files

RED:
- New file `tests/test_runtime_v3.py`: 14 test functions, 17 cases with parametrization. Before the source change, 16 cases failed for the expected reasons: no Git root lookup, no `sticky_target`, retry mutated the source row, `next_target` was an `nt_` token, no result file. `test_retry_from_active_state_is_invalid_state` passed on HEAD and stays as a characterization test.

GREEN:
- PYTEST: 1133 passed, 15 deselected. Since 4A: 17 cases added, 12 tests and 1 parametrized case deleted.
- PLUGIN: pass. LINES: 12047. Ruff F: no new findings against HEAD.

Changes:
- `runtime.py`: `resolve_project` runs `git -C <path> rev-parse --show-toplevel` as an argv list with a 10 s timeout. A path outside Git fails with `invalid_path`. `job.project` is the Git root path.
- `database.py`: `_finish` upserts `sessions.sticky_target` for the job's project, session and workflow when the state is `succeeded`, in the same transaction as the finish. New `sticky_target()` reader.
- `execution.py`: `TargetExecutor.execute` moves the sticky target to the front of the profile order when it is still in the profile. The circuit check then applies as before, so an open sticky target falls through to profile order.
- Retry: `Runtime.retry(job_id, target="")` creates a new job with a new ID and `retry_of` set to the source. It copies prompt, session, profile and `fresh` from the source. Accepted source states: `succeeded`, `failed`, `cancelled`, `interrupted`. Any other state fails with `invalid_state`. The source row is never written. `Database.reset_retry` and `telemetry.prepare_telemetry_for_retry` are deleted.
- Retry target: `target=X` pins X, including the source's own target. An unknown X fails with `invalid_request` listing the profile's targets. With no `target`, the new job is pinned to the first target after the source's target in profile order whose circuit is closed.
- `next_target` is the plain id of that following target. `planning.next_target_token`, `planning.resolve_next_target` and the token check in `submit` are deleted.
- Result files: every terminal finish writes the result text to `<state dir>/results/<job_id>.md`, file mode 0600 in a 0700 directory. `Database.result_path(job_id)` returns the path.
- `server.py`: `job_submit` lost its `next_target` parameter. The rest of the v2 surface stays until 4C.

Deviations:
- Retry with no `target` when no target follows the source's target fails with non-retryable `targets_unavailable`, and `next_action` lists the profile's targets. When following targets exist but all circuits are open, it fails with retryable `targets_unavailable` and `retry_after_s`, the same as `submit`. DESIGN.md does not cover either case.
- Single-target retry now needs `target=` explicitly, because `retry(job_id)` means "next target". Existing single-target retry tests were changed to pass `target="primary"` and wait on the new job ID.
- The result file is written for every terminal state, including empty text.
- Deleted tests that pinned same-row retry behavior: 4 in `test_database.py` covering retry telemetry roll-over and revision, the `retry` case in `test_database_atomicity.py`, `test_retry_uses_actual_attempt_number` in `test_execution.py`. The schema-15 telemetry test kept its migration part and dropped the retry part.
- Deleted 7 token tests in `test_runtime.py` ahead of 4C: the `report_error` routing tests and the token binding and validation tests. `test_job_report_error_mcp_serializes_eligible_output_recovery` now expects the plain name `b`.
- Tests that registered plain directories now run `git init` first.

Debt:
- Result files are never pruned. Retention belongs to Phase 5.
- `Runtime.report_error` still exists for the v2 `job_report_error` tool. Step 4C deletes both.

## Step 4C: six MCP tools

Owner decisions 2026-11-04:
- The `failure_kind` value `retryable` is renamed to `transient`. Every `retryable` field and variable is removed, so the acceptance grep `retryable\b` prints nothing in `server/src`. DESIGN.md needs the same edit.
- A job whose config cannot load reports `failure_kind` `request_fatal`. `config_invalid` leaves `FAILURE_KINDS`. DESIGN.md enum stays as written apart from the rename.

RED:
- `tests/test_mcp_schema_contract.py`: the three v2 schema tests were replaced with 7 v3 tests: exact six tool names and input schemas, `FAILURE_KINDS` equals the DESIGN set with `transient`, list/submit/wait from a subdirectory with exact `job`, `result` and `tokens` keys, submit and list outside Git give `invalid_path`, long result truncated with full text at `result_path`, failed job reports `transient` and retry returns a new job with `retry_of`, cancel and answer return `{job}` or a compact error. Every payload is scanned for removed keys. Error payload keys must be within `code, message, next_action, retry_after_s`.
- All 7 failed on HEAD for the expected reasons: v2 tool names, `retryable` and `config_invalid` in `FAILURE_KINDS`, `retryable` in error payloads, unknown tool names. The two generic SDK guard tests still pass.

GREEN plan:
- `server.py`: delete `project_resolve`, `task_guide`, `job_list`, `job_report_error`, `_FORBIDDEN_OUTPUT_KEYS`, `_public_data` redaction, `_page_terminal_result`, `result_offset`, `_public_terminal_error`. Tools `submit(path, workflow, prompt, profile, session, fresh)`, `wait(job_id, timeout_s=3600)`, `answer`, `cancel`, `retry(job_id, target)`, `list(path)`. `list` and `submit` call `runtime.resolve_project(path)`. Public job dict: `id, project` as the project root path, `workflow, profile, target` as `job.target_id`, `session, state, retry_of, created_at, updated_at`. Result dict: `text` cut by halving until the payload fits `_fits_response`, `truncated`, `result_path` from `Database.result_path` on terminal jobs or null, `pending_question` as `{question_id, text}` or null, `failure_kind` or null, `next_target` from `Runtime._next_target` for failed or cancelled jobs or null, `model`, `duration_ms`, `tokens` with `context_used, context_window, input, output, cache_read, cache_write` as int or null from the telemetry measurement values. `RefractError` loses `retryable`; `_ERROR_FIELDS = {code, message, next_action}`; `retry_after_s` only on `targets_unavailable`. Rewrite `_INSTRUCTIONS` for the six tools. Error `next_action` strings that name v2 tools must name the v3 tools.
- `result_metadata.py`: `FAILURE_KINDS` and `FailureKind` become cancelled, circuit_open, context_overflow, replay_blocked, request_fatal, target_fatal, transient. `RetryMetadata.retryable` is removed. Stored rows still hold `failure.kind` `retryable` or `config_invalid` and `retry.retryable`: map them on read to `transient` and `request_fatal` and drop `retry.retryable` before validation, where `job_view` parses metadata. Phase 5 replaces this storage.
- `runtime.py`, `execution.py`: `OrchestrationError` loses `retryable`; rename the internal `retryable` variables; `live_result_metadata` and `report_error` lose the `retryable` field; delete `Runtime.report_error` and `Database.record_error_report` if orphaned. Where `config_invalid` was a failure kind, use `request_fatal`.
- Tests: rewrite or delete v2-tool tests in `test_server.py`, `test_async_workers.py` and others that call `project_resolve`, `task_guide`, `job_list`, `job_report_error`, `job_*` names, `result_offset`, `retryable`.

GREEN:
- The 7 contract tests pass. Full suite: 1111 passed, 15 deselected. PLUGIN passes. LINES 11735, down from 12047. Ruff F against HEAD: no new findings; two pre-existing `Any` F821 findings are gone.
- Acceptance grep prints only the `task_guide.json` file name in `config.py`, which PLAN.md allows.

Changes:
- `server.py`: six tools `submit`, `wait`, `answer`, `cancel`, `retry`, `list` with the DESIGN shapes; long text cut until the payload fits, full text at `result_path`; `_INSTRUCTIONS` rewritten; error payload `{code, message, next_action}` plus `retry_after_s` on `targets_unavailable`.
- `result_metadata.py`: seven failure kinds with `transient`; `RetryMetadata.retryable` removed; `normalize_stored_metadata` maps stored `retryable` and `config_invalid` on read.
- `runtime.py`, `execution.py`: `retryable` removed from `OrchestrationError` and metadata; `transient` and `request_fatal` kinds; `Runtime.report_error` deleted.
- `database.py`: `job_overview` replaces `job_listing`; `record_error_report` deleted.
- `config.py`: `load_task_guide` renamed `load_guidance`; a missing guidance file returns None.
- `models.py`: matching field updates.
- DESIGN.md failure kind list uses `transient` and records the read-time mapping.
- Tests: net 22 fewer than 4B. Deleted tests covered paging, opaque tokens, error reports, output redaction and v2-only summaries. Tests of surviving behavior were ported to the v3 names. One added: `test_wait_response_truncates_long_text_and_keeps_result_path` in `test_server.py`, plus the read-time mapping case in `test_result_metadata.py`.

Deviations:
- GREEN was done by a Claude subagent in this worktree to keep context small. It is not a Refract job. Results were rerun and checked before commit.
- Schema 15 and 16 fixtures and `RetryMetadata(retryable=...)` rejection inputs stay in tests to cover migration and extra-field rejection.

Debt:
- The `error_reports` table DDL stays until the Phase 5 storage rebuild.
- Read-time mapping of stored failure kinds goes away with the Phase 5 storage rebuild.

## Step 4D: ask fixes

RED:
- `tests/test_ask.py::test_answer_after_question_deadline_is_rejected`: with a fake clock past the question deadline, `deliver_answer` returned True on HEAD and the worker got the late answer.
- `tests/test_ask.py::test_revoked_tokens_are_not_retained`: HEAD kept every revoked token in `_revoked_tokens` and deadlines in a separate dict.
- `tests/test_ask.py::test_ask_client_timeout_is_ask_timeout_plus_ten`: HEAD called `urlopen` with no timeout, so `refract ask` could hang forever on an unresponsive server.
- `test_execution_attempt_injects_and_revokes_token_and_keeps_secret` now also asserts `REFRACT_ASK_TIMEOUT_S`; it failed on HEAD with `KeyError`.

GREEN:
- 15 ask tests pass. Full suite: 1114 passed, 15 deselected. PLUGIN passes. LINES 11746. Ruff F against HEAD: no new findings.

Changes:
- `ask.py`: each token record is `_Token(value, deadline)`; `_revoked_tokens` and `_deadlines` are deleted, so a revoked token is simply unknown. `PendingQuestion.deadline` holds the question deadline. `deliver_answer` checks and resolves under the registry lock and returns False when the question is missing, done, or past its deadline. `_resolve_future` sets the result directly when called on the future's own loop, so an answer cannot be lost between delivery and the timeout.
- `runtime.py`: the `invalid_state` message for `answer` says the question is not pending or expired.
- `execution.py`: workers get `REFRACT_ASK_TIMEOUT_S` with the configured `ask_timeout_s`.
- `cli.py`: `refract ask` uses `urlopen(..., timeout=REFRACT_ASK_TIMEOUT_S + 10)`, defaulting to `DEFAULT_ASK_TIMEOUT_S`. A timeout reports "Coordinator connection failed."

Deviations:
- The client learns `ask_timeout_s` through a new `REFRACT_ASK_TIMEOUT_S` worker variable. The worker process may not see the daemon's config file, so reading config in the client was not reliable. The variable uses the reserved `REFRACT_ASK_` prefix that config already protects.
- `PendingQuestion` is still built outside the lock and gets its deadline under the lock, because `test_ask_atomic_validation_and_registration_rejects_revoked_token` revokes the token during construction.

Debt: none.

## Step 4E: plugin and docs

**RED:** `plugin/tests/test-contracts.sh` was rewritten first to parse the six-row `## Six tools` table in `tool-contract.md`, check the error set, and forbid v2 tool names built from split literals. It failed against the v2 skills. `test-session-start.sh` gained one assertion for the `list` reference in the hook context.

**GREEN:** PLUGIN passes. PYTEST 1114 passed, 15 deselected. Both name checks are clean: the Phase 4 acceptance grep prints only the `task_guide.json` file name in `config.py`, and `git grep -nE 'job_submit|job_wait|job_answer|job_cancel|job_retry|project_id' -- plugin README.md server/README.md` prints nothing.

**Changes:**
- `tool-contract.md` rewritten for submit, wait, answer, cancel, retry, list, with a recovery section.
- Skills `coordinating-multi-model-work` with `references/review.md` and `references/handover.md`, `executing-plans` with `implementer-prompt.md`, `writing-plans`, `setting-up-refract`, `using-git-worktrees`: `list(path)` replaces project resolution and task guide calls; `session` and `fresh` replace the v2 names; recovery uses `retry` and `failure_kind`; truncated results point at `result_path`.
- `review.md`: "Diagnostic anomalies" replaced by "Unusable output", which uses `retry`.
- `plugin/hooks/refract-session-start.sh` points at `list` guidance.
- `server/README.md` tool surface and "Recovery and Routing" sections; `server/CLI_ARGUMENTS.md` ask paragraph.
- `server.py` MCP instructions: retry accepts succeeded, failed, cancelled, and interrupted jobs, matching the runtime and the contract.
- DESIGN.md: `fresh_session=true` replaced by `fresh=true` in flow item 3 and the failure table.

**Deviations:** Step 4E edits ran in a Claude subagent in the same worktree to save context. The coordinator reran PYTEST, PLUGIN, and both name checks before commit. `plugin/pi/extensions/refract.ts` needed no change.

**Debt:** `server/README.md` sections "Worker Telemetry and Context Measurement" and "Worker Live Dashboard Streaming", and the telemetry section in `server/CLI_ARGUMENTS.md`, still describe `result.metadata` groups. Phase 5 deletes the measurement model and rewrites them.
