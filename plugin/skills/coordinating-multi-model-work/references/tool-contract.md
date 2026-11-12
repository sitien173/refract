# Refract Tool Contract

Follow these rules for every Refract MCP call. Default endpoint is `http://127.0.0.1:8765/mcp`.

## Nine tools

| Tool | Parameters | Returns |
|---|---|---|
| `submit` | `path`, `workflow`, `prompt`, `profile=""`, `session=""`, `fresh=false` | `{job}` |
| `wait` | `job_id`, `timeout_s=3600` | `{job, result}` |
| `answer` | `job_id`, `answer` | `{job}` |
| `cancel` | `job_id` | `{job}` |
| `retry` | `job_id`, `target=""` | `{job}` for a new job with `retry_of` set |
| `list` | `path` | `{active, recent, workflows, profiles, guidance}` |
| `card_create` | `path`, `title`, `body=""`, `job_ids=()` | `{card}` |
| `card_move` | `card_id`, `state`, `job_ids=()`, `note=""` | `{card, moved}` |
| `card_list` | `path` | `{cards, truncated, omitted}` |

Call only these tools with only these parameters. They belong to the `refract` MCP server; never call a same-named tool from another server. Unknown tool arguments return `invalid_request`. Capture `job.id` from returned envelopes.

- `job`: `id, project, workflow, profile, target, session, state, retry_of, created_at, updated_at`. `project` is the Git root path.
- `result`: `text, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens`.
- `tokens`: `context_used, context_window, input, output, cache_read, cache_write`, each an integer or null.

## Standard cycle

1. Call `list(path)` once per phase. `path` is any directory inside the project; Refract resolves its Git root. A path outside Git returns `invalid_path`.
2. Call `submit` with the same `path` and a self-contained `prompt`.
3. Call `wait(job_id)` until the job is terminal, then read `result.text`.

## Choosing workflow and profile

- `list` takes no phase argument. Put the complete request in `submit.prompt`.
- Choose `workflow` from `workflows` and `profile` from `profiles.available`. Omit `profile` to use `profiles.default`.
- Profiles may be partial. `other` requires an explicit mapping and never falls back. Follow returned guidance or error for unsupported mappings; never invent a replacement.

## Admission

Jobs are admitted FIFO up to the global `max_jobs` capacity, and jobs in the same project may run concurrently. Concurrent jobs share the project checkout and can edit the same files. Jobs that share a project, `session`, workflow, and target run one at a time.

## Sessions

- Always start every phase with `fresh=true`, summarizing prior state and including full role contracts plus the phase prompt path. Also start with `fresh=true` after `failure_kind` `context_overflow` or when `result.tokens.context_used` exceeds 150,000.
- For follow-up jobs within the same phase, workflow, and `session`: if `context_used` is below 150,000 or null, omit `fresh` and send only the delta; do not invent usage.
- A fresh job runs your prompt without a stored session and replaces the stored session on success.
- A resumed job uses the stored worker session. Refract stores no prompt or response history.
- A successful job makes its target the session's preferred target; later jobs in that session try it first, then profile order.
- Changing project, `session`, or workflow starts a separate session.

## Waiting and results

- Call `wait` with its 3600-second default. `timeout_s` accepts 0..3600.
- Treat timeouts as normal; repeat only while nonterminal. Wait sequentially, one call per job, without polling or overlapping calls. Re-wait on the same job ID after dropped connections.
- Exception: while more than one wave job is active, wait round-robin with `timeout_s=60` per [waves.md](waves.md#waiting).
- When `wait` returns early with `result.pending_question` (`{question_id, text}`), call `answer(job_id, answer)` (max 8192 characters). For large context, write it to a file and tell the worker to read the path. `answer` without a pending question, after the question expired, or on a terminal job returns `invalid_state`.
- Every terminal job writes its full text to `result.result_path`. When `result.truncated` is true, read the full text from that file.
- `failure_kind` is null on success, else one of `cancelled`, `circuit_open`, `replay_blocked`, `context_overflow`, `request_fatal`, `target_fatal`, `transient`.

Responses stay below 30,000 characters and 9,000 UTF-8 bytes. If a mutation response overflows, report the actual outcome and keep the job ID. Never blindly resubmit.

## Recovery

- `retry(job_id)` creates a new job on `result.next_target`, the next healthy target in profile order after the job's target. It never changes the source job. It accepts `succeeded`, `failed`, `cancelled`, and `interrupted` jobs.
- The new job from `retry` keeps the source job's `session` and `fresh` values.
- `retry(job_id, target=X)` pins target X, including the same target. An unknown target returns `invalid_request` that lists the profile's targets.
- On `context_overflow`, summarize state and `submit` again with `fresh=true`.
- On `replay_blocked`, the worker already changed files. Inspect the worktree before any retry.
- Otherwise, report the failure.

## Listing and lost jobs

`list` returns active jobs and the newest terminal jobs. If a saved job is absent from the list, call `wait(saved_id, timeout_s=0)` before treating it as unknown. Absence never authorizes duplicate submission.

## Errors

Expected failures return compact JSON with `isError: true` and `code`, `message`, `next_action`. `targets_unavailable` also carries `retry_after_s`. Follow `next_action`.

| Code | Safe next action |
|---|---|
| `invalid_path` | Supply a directory inside a Git repository. |
| `unknown_job` | Reconcile with `list`; do not duplicate. |
| `unknown_profile` | Call `list` and select a listed profile. |
| `invalid_state` | Inspect with `wait`; submit a new job if needed. |
| `config_invalid` | Report for correction in the dashboard. |
| `daemon_stopping` | Wait, then call `list` again. |
| `invalid_request` | Match the schema; pick a listed target. |
| `targets_unavailable` | Wait at least `retry_after_s` seconds before retrying. |
| `response_too_large` | Honor the applied outcome and job ID; do not blindly retry. |
| `unknown_card` | Call `card_list` to find the card ID. |
| `internal_error` | Retry once, then report the request ID only. |
