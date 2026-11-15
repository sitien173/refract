# Refract Tool Contract

Follow these rules for every Refract MCP call. Default endpoint is `http://127.0.0.1:8765/mcp`.

## Nine tools

| Tool | Parameters | Returns |
|---|---|---|
| `submit` | `path`, `workflow`, `prompt`, `profile=""`, `session=""`, `fresh=null`, `from_job=""`, `target=""` | `{job}` |
| `get` | `job_id` | `{job, result, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens, attempts}` |
| `wait` | `job_ids`, `timeout_s=3600` | `{job, result, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens}` |
| `cancel` | `job_id` | `{job, cancel_status}` |
| `answer` | `job_id`, `answer` | `{job}` |
| `list` | `path` | `{active, recent, workflows, profiles, guidance}` |
| `card_create` | `path`, `title`, `body=""`, `job_ids=()` | `{card}` |
| `card_move` | `card_id`, `state`, `job_ids=()`, `note=""` | `{card, moved}` |
| `card_list` | `path` | `{cards, truncated, omitted}` |

Call only these tools with only these parameters. They belong to the `refract` MCP server; never call a same-named tool from another server. Unknown tool arguments return `invalid_request`. Capture `job.id` from returned envelopes.

- `job`: `id, project, workflow, profile, target_id, session, state, from_job, created_at, updated_at`. `project` is the Git root path.
- `result` is the job text. `truncated`, `result_path`, `pending_question`, `failure_kind`, `next_target`, `model`, `duration_ms`, and `tokens` sit beside `job` and `result`.
- `attempts`: one entry per attempt with `seq, reason, target, backend, model, state, failure_kind, replay_safe, started_at, finished_at, duration_ms, tokens`. `reason` is `initial`, `retry`, `fresh_session`, or `fallback`.
- `submit` with `from_job` takes only `path`, `target`, and `fresh`. `cancel_status` is `terminated` (queued), `requested` (running), or `already_terminal`, which `cancel` never changes.
- `tokens`: `context_used, context_window, input, output, cache_read, cache_write`, each an integer or null.

## Standard cycle

1. Call `list(path)` once per phase. `path` is any directory inside the project; Refract resolves its Git root. A path outside Git returns `invalid_path`.
2. Call `submit` with the same `path` and a self-contained `prompt`.
3. Call `wait(job_ids)` until the job is terminal, then read `result`.

## Choosing workflow and profile

- `list` takes no phase argument. Put the complete request in `submit.prompt`.
- Choose `workflow` from `workflows` and `profile` from `profiles.available`. Omit `profile` to use `profiles.default`.
- Profiles may be partial. `other` requires an explicit mapping and never falls back. Follow returned guidance or error for unsupported mappings; never invent a replacement.

## Admission

Jobs are admitted FIFO up to the global `max_jobs` capacity, and jobs in the same project may run concurrently. Concurrent jobs share the project checkout and can edit the same files. Jobs that share a project, `session`, workflow, and target run one at a time.

## Sessions

- Always start every phase with `fresh=true`, summarizing prior state and including full role contracts plus the phase prompt path. Also start with `fresh=true` after `failure_kind` `context_overflow` or when `tokens.context_used` exceeds 150,000.
- For follow-up jobs within the same phase, workflow, and `session`: if `context_used` is below 150,000 or null, omit `fresh` and send only the delta; do not invent usage.
- A fresh job runs your prompt without a stored session and replaces the stored session on success.
- A resumed job uses the stored worker session. Refract stores no prompt or response history.
- A successful job makes its target the session's preferred target; later jobs in that session try it first, then profile order.
- Changing project, `session`, or workflow starts a separate session.

## Waiting and results

- Call `wait` with its 3600-second default. `timeout_s` accepts 0..3600.
- `wait(job_ids)` takes 1 to 16 distinct IDs and returns the first ready job. Treat timeouts as normal; repeat only while nonterminal. Wait sequentially, one call per job, without polling or overlapping calls. Re-wait on the same job ID after dropped connections.
- Exception: while more than one wave job is active, wait round-robin with `timeout_s=60` per [waves.md](waves.md#waiting).
- When `wait` returns early with `pending_question` (`{question_id, text}`), call `answer(job_id, answer)` (max 8192 characters). For large context, write it to a file and tell the worker to read the path. `answer` without a pending question, after the question expired, or on a terminal job returns `invalid_state`.
- A result that exceeds the byte limit is truncated. The response then carries `truncated: true` and `result_path`; when `truncated` is true, read the full text from `result_path`.
- `failure_kind` is null on success, else one of `cancelled`, `circuit_open`, `context_overflow`, `request_fatal`, `target_fatal`, `transient`.

Responses stay below 30,000 characters and 9,000 UTF-8 bytes. If a mutation response overflows, report the actual outcome and keep the job ID. Never blindly resubmit.

## Recovery

- `submit(from_job=X)` copies a `succeeded`, `failed`, `cancelled`, or `interrupted` job and never changes it. Without `target`, it uses `next_target`, the next healthy target in profile order after the source job's last attempt. It keeps the source job's `session`; `fresh` copies the source job unless set. `fresh` defaults to null. Without `from_job`, null means false. With `from_job`, omitting `fresh` copies the source job's value, and an explicit `fresh=false` overrides a source job that used `fresh=true`.
- `submit(from_job=X, target=Y)` pins target Y, including the same target. A source job that is not terminal or was pruned returns `invalid_state`.
- When an attempt is `replay_safe`, the server retries on the same target, opens a fresh session on `context_overflow`, and falls back to the next target on its own, recording each step in `attempts`. Do not repeat that recovery.
- A failure outside that recovery, such as a worker that already ran a tool or asked a question, leaves the job failed. Inspect the worktree before any `submit(from_job=...)`. After `context_overflow`, summarize state and `submit` again with `fresh=true`. Otherwise, report the failure.

## Listing and lost jobs

`list` returns active jobs and the newest terminal jobs. If a saved job is absent from the list, call `get(saved_id)` before treating it as unknown. Absence never authorizes duplicate submission.

## Errors

Expected failures return compact JSON with `isError: true` and `code`, `message`, `next_action`. `targets_unavailable` also carries `retry_after_s`. Follow `next_action`.

| Code | Safe next action |
|---|---|
| `invalid_path` | Supply a directory inside a Git repository. |
| `unknown_job` | Reconcile with `list`; do not duplicate. |
| `unknown_profile` | Call `list` and select a listed profile. |
| `invalid_state` | Inspect with `get`; submit a new job if needed. |
| `config_invalid` | Report for correction in the dashboard. |
| `daemon_stopping` | Wait, then call `list` again. |
| `invalid_request` | Match the schema; pick a listed target. |
| `targets_unavailable` | Wait at least `retry_after_s` seconds before retrying. |
| `response_too_large` | Honor the applied outcome and job ID; do not blindly retry. |
| `unknown_card` | Call `card_list` to find the card ID. |
| `internal_error` | Retry once, then report the request ID only. |
