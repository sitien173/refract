# Refract Tool Contract

Follow these rules for every Refract MCP call. Default endpoint is `http://127.0.0.1:8765/mcp`.

## Nine tools

| Tool | Parameters | Returns |
|---|---|---|
| `project_resolve` | `path`, `alias=""` | `{project:{id, alias, path}}` |
| `task_guide` | `project_id` | `{workflows, profiles:{default, available}, guidance}` |
| `job_submit` | `project_id`, `workflow`, `prompt`, `profile=""`, `context_key=""`, `fresh_session=false`, `next_target=""` | `{job:summary}` |
| `job_wait` | `job_id`, `timeout_s=3600`, `result_offset=0` | `{job:summary, result:{text, error, next_offset, metadata}}` |
| `job_list` | `project_id` | `{active, recent, more_recent}` |
| `job_cancel` | `job_id` | `{job:summary}` |
| `job_retry` | `job_id` | `{job:summary}` |
| `job_answer` | `job_id`, `answer` | `{job:summary}` |
| `job_report_error` | `job_id`, `category`, `expected`, `observed`, `report_key` | `{report:{id, job_id, category, created_at}, duplicate}` |

Call only these tools with only these parameters; your client may prefix the names. Unknown tool arguments return `invalid_request`. Capture `project.id` and `job.id` from returned envelopes.

## Standard cycle

1. Call `project_resolve(path=...)` with the existing Git-root directory. Refract never walks up to find the root. Omit `alias` unless needed.
2. Call `task_guide(project_id)` once per phase.
3. Call `job_submit` with a self-contained `prompt`.
4. Call `job_wait(job_id)` until terminal, then page the result.

## Choosing workflow and profile

- `task_guide` takes no phase argument. Put the complete request in `job_submit.prompt`.
- Choose `workflow` from `workflows` and `profile` from `profiles.available`. Omit `profile` to use `profiles.default`.
- Profiles may be partial. `other` requires an explicit mapping and never falls back. Follow returned guidance or error for unsupported mappings; never invent a replacement.

## Admission

At most one job per project runs at a time. Jobs within each project are admitted FIFO, bounded by the global `max_jobs` capacity; jobs in different projects may run concurrently up to that capacity.

## Sessions

- Always start every phase with `fresh_session=true`, summarizing prior state and including full role contracts plus the phase prompt path. Also start with `fresh_session=true` when `context_overflow` occurred or when `result.metadata.telemetry.context_used_tokens.value` exceeds 150,000 tokens.
- For follow-up jobs within the same phase, workflow, and `context_key`: if `context_used_tokens.value` is below 150,000 tokens, or if `value` is null or unavailable, omit `fresh_session` and send only the delta; do not invent usage.
- A fresh job runs your prompt without stored history and replaces the stored session on success.
- A resumed job uses the stored session, or bounded turn history when none exists. `job_retry` keeps the original `fresh_session` setting.
- Changing project, `context_key`, workflow, or configured target starts a separate session.

## Waiting, paging, and bounds

- Call `job_wait` with its 3600-second heartbeat default. `timeout_s` accepts 0..3600. `result_offset` is a nonnegative Unicode code-point offset, default 0.
- Treat timeouts as normal; repeat only while nonterminal. Wait sequentially, one call per job, without polling or overlapping calls. Re-wait on the same job ID after dropped connections.
- When `job_wait` returns early with `result.pending_question` (`{question_id, text}`), call `job_answer(job_id, answer)` (max 8192 characters). For large context, write it to a file and tell the worker to read the path. Calling `job_answer` without a pending question or on a terminal job returns `invalid_state`.

To read a terminal result, keep `result.text` and call `job_wait(job_id, timeout_s=0, result_offset=<result.next_offset>)` until `next_offset` is null. Concatenate all pages.

Every terminal page includes canonical grouped `result.metadata`: `execution` (`model`, `duration_ms`), `failure` (`null` or `{kind}`), `retry` (`retryable`, `next_target`), and `telemetry` (`completeness`, `context_remaining_percent`, `context_window_size`, `context_used_tokens`, `total_input_tokens`, `total_output_tokens`, `cache_read_tokens`, `cache_write_tokens`). Measurements contain value, source, quality, and observed_at. `failure.kind` is `cancelled`, `circuit_open`, `replay_blocked`, `context_overflow`, `request_fatal`, `target_fatal`, or `retryable`.

On failure, pass `result.metadata.retry.next_target` unchanged to `job_submit(next_target=...)`; on `invalid_request`, resubmit without it. On `context_overflow`, summarize state and resubmit with `fresh_session=true`. Otherwise, report the failure.

Responses stay below 30,000 characters and 9,000 UTF-8 bytes. If a response overflows after an applied mutation, report the actual outcome and keep the root job or project ID. Never blindly resubmit.

## Listing and lost jobs

`job_list` returns active jobs, the ten newest terminal jobs, and `more_recent` (older terminal job count, not a cursor). Summary fields are exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`.

If a saved job is absent from the list, call `job_wait(saved_id, timeout_s=0)` before treating it as unknown. Absence never authorizes duplicate submission.

## Diagnostic reporting

Call `job_report_error(job_id, category, expected, observed, report_key)` for anomalies. Summaries span 1 to 2048 characters; keys span 1 to 128 ASCII chars. Use unique opaque keys per observation. Reusing a key with different content returns `invalid_request`. Matching content returns duplicate acknowledgement. Reports are client observations; they never alter execution state. Redact secrets first; only correlation IDs are logged. Pruning follows `Database.prune_history` on `updated_at`. Reports vanish while jobs remain. Distinguish wait timeouts, pending questions, and partial pagination. Await complete terminal pagination before reporting missing output. Generic worker error text under `succeeded` is an output-report example. Require ERP only where the workflow demands it.

## Errors

Expected failures return compact JSON with `isError: true` and `code`, `message`, `retryable`, `next_action`. Follow `next_action` and retry only when `retryable` is true.

| Code | Safe next action |
|---|---|
| `unknown_project` | Resolve the Git root with `project_resolve`. |
| `invalid_path` | Supply an existing absolute directory. |
| `alias_taken` | Choose a unique alias or omit it. |
| `unknown_job` | Reconcile with `job_list`; do not duplicate. |
| `unknown_profile` | Call `task_guide` and select a listed profile. |
| `invalid_state` | Inspect with `job_wait`; submit a new job if needed. |
| `config_invalid` | Report for correction in the dashboard. |
| `daemon_stopping` | Wait, then resolve the Git root again. |
| `invalid_request` | Match the schema; omit stale `next_target`. |
| `targets_unavailable` | Wait at least `retry_after_s` seconds before retrying. |
| `response_too_large` | Honor applied outcome and root ID; do not blindly retry. |
| `internal_error` | Retry once, then report the request ID only. |
