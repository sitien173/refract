# Refract Tool Contract

Follow these rules for every Refract MCP call. Default endpoint is `http://127.0.0.1:8765/mcp`;

## Seven tools

| Tool | Parameters | Returns |
|---|---|---|
| `project_resolve` | `path`, `alias=""` | `{project:{id, alias, path}}` |
| `task_guide` | `project_id` | `{workflows, profiles:{default, available}, guidance}` |
| `job_submit` | `project_id`, `workflow`, `prompt`, `profile=""`, `context_key=""`, `fresh_session=false`, `next_target=""` | `{job:summary}` |
| `job_wait` | `job_id`, `timeout_s=3600`, `result_offset=0` | `{job:summary, result:{text, error, next_offset, metadata}}` |
| `job_list` | `project_id` | `{active, recent, more_recent}` |
| `job_cancel` | `job_id` | `{job:summary}` |
| `job_retry` | `job_id` | `{job:summary}` |

Call only these tools with only these parameters; your client may prefix the names. Unknown tool arguments return `invalid_request`. Capture `project.id` and `job.id` from returned envelopes.

## Standard cycle

1. Call `project_resolve(path=...)` with the actual, existing Git-root directory. Refract never walks up to find the root. Omit `alias` unless you need one.
2. Call `task_guide(project_id)` once per phase.
3. Call `job_submit` with a self-contained `prompt`.
4. Call `job_wait(job_id)` until terminal, then page the result.

A terminal one-page result takes four calls; resume, recovery, nonterminal waits, and paging add calls.

## Choosing workflow and profile

- `task_guide` takes no phase argument. Put the complete request in `job_submit.prompt`.
- Choose `workflow` from `workflows` and `profile` from `profiles.available`. Omit `profile` to use `profiles.default`.
- Profiles may be partial. `other` requires an explicit mapping and never falls back. For an unsupported mapping, follow the returned guidance or error; never invent a replacement.
- For `consult` and `review`, choose a configured read-only target: workflow names do not enforce write safety.

## Privacy and ownership

- Never send provider, model, configured target, or native session identity. Tell workers to edit only declared scope.
- You own Git, anchors, gates, review, and handover. Refract and its workflows never commit, reset, restore, stash, clean, integrate, or call Git for you.

## Sessions

- First plan `implement` and `review` jobs: set `fresh_session: true` and send full role contracts.
- Later jobs with the same workflow and `context_key`: omit `fresh_session`. Send only the delta plus the phase prompt path.
- A fresh job gets your prompt verbatim without stored history; on success it replaces the stored session.
- A standard job resumes the stored session, or gets bounded turn history when none exists. `job_retry` keeps the original `fresh_session` setting.
- Changing project, `context_key`, workflow, or configured target starts a separate session.

## Admission

At most one job per project runs at a time. Jobs within each project are admitted FIFO, bounded by the global `max_jobs` capacity; jobs in different projects may run concurrently up to that capacity. A queued job is normal; wait for it. Never run concurrent gated implementation or review in one root.

## Waiting, paging, and bounds

- Call `job_wait` with its 3600-second heartbeat default. `timeout_s` accepts 0..3600. `result_offset` is a nonnegative Unicode code-point offset, default 0.
- Wait sequentially, one call per job. Do not use short hardcoded waits, polling, sleeps, or overlapping calls.
- Treat a timeout as normal, not failure. Repeat only while nonterminal; nonterminal text is empty and the offset does not advance.
- After a dropped connection, wait again on the same job ID.

To read a terminal result, keep `result.text`, then call `job_wait(job_id, timeout_s=0, result_offset=<result.next_offset>)` until `next_offset` is null. Concatenate every page.

Every terminal page includes `result.metadata` with `model_name, context_window_max, context_window_used, input_tokens, output_tokens, cached_input_tokens, duration_ms, failure_kind, retryable, next_target`. Unreported values are null. `failure_kind` is one of `cancelled, circuit_open, replay_blocked, context_overflow, request_fatal, target_fatal, retryable`.

On failure, if `next_target` is a token, pass it unchanged to `job_submit(next_target=...)`; on `invalid_request`, resubmit without it. For `context_overflow`, resubmit with `fresh_session=true`. Otherwise, report the failure.

Every response stays below 30,000 characters and 9,000 UTF-8 bytes. If a response overflows after an applied mutation, report its actual outcome and keep the root job or project ID. Never blindly resubmit.

## Listing and lost jobs

`job_list` returns every active job, the newest ten terminal jobs, and `more_recent`, an integer count of older terminal jobs. It is not a cursor. Summary fields are exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`.

If a saved job is absent from the list, call `job_wait(saved_id, timeout_s=0)` before treating it as unknown. Absence never authorizes duplicate submission.

## Errors

Expected failures are compact JSON with `isError: true` and `code`, `message`, `retryable`, `next_action`. Follow `next_action`. Retry only when `retryable` is true and the action allows it.

| Code | Safe next action |
|---|---|
| `unknown_project` | Resolve the supplied Git root with `project_resolve`. |
| `invalid_path` | Supply an existing absolute directory. |
| `alias_taken` | Choose a unique alias or omit it. |
| `unknown_job` | Reconcile using `job_list`; do not blindly duplicate. |
| `unknown_profile` | Call `task_guide`; select a listed profile. |
| `invalid_state` | Inspect using `job_wait`; use a new job if appropriate. |
| `config_invalid` | Report for correction in the dashboard. |
| `daemon_stopping` | Wait, then resolve the Git root again. |
| `invalid_request` | Correct arguments to the declared schema; for an unknown or stale `next_target`, resubmit without `next_target`. |
| `targets_unavailable` | Wait at least `retry_after_s` seconds, an integer, before retrying. Returned by `job_submit` and `job_retry`. |
| `response_too_large` | Inspect or reduce metadata; honor the applied outcome and root ID; no blind retry. |
| `internal_error` | Retry once, then report the request ID only. |
