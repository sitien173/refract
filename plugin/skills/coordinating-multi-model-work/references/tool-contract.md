# OpenMCP v2 Tool Contract

Default endpoint is `http://127.0.0.1:8765/mcp`; set `OPENMCP_URL` before Claude Code starts.

## Seven tools

| Tool | Parameters | Returns |
|---|---|---|
| `project_resolve` | `path`, `alias=""` | `{project:{id, alias, path}}` |
| `task_guide` | `project_id` | `{workflows, profiles:{default, available}, guidance}` |
| `job_submit` | `project_id`, `workflow`, `prompt`, `profile=""`, `context_key=""`, `fresh_session=false`, `depends_on=[]` | `{job:summary}` |
| `job_wait` | `job_id`, `timeout_s=3600`, `result_offset=0` | `{job:summary, result:{text, error, next_offset}}` |
| `job_list` | `project_id` | `{active, recent, more_recent}` |
| `job_cancel` | `job_id` | `{job:summary, cancelled_dependents:[id]}` |
| `job_retry` | `job_id` | `{job:summary}` |

Use only these signatures; client names may be prefixed. Capture `project.id` and `job.id` from returned envelopes. Pass `project_resolve` the actual, existing Git-root directory: it canonicalizes that directory but never walks up to find the root. `alias` defaults to empty.

## Guidance, routing, and privacy

`task_guide(project_id)` returns public `workflows`, `profiles.default`, `profiles.available`, and `guidance`; it has no phase-request argument. Put the complete request in self-contained `job_submit.prompt`. Profiles may be partial. `other` requires an explicit mapping and never falls back. Validate public names only; handle unsupported mappings through actual guidance/errors, never invent a replacement.

Keep provider, model, configured target, and native session identity private; native identity is not client input. Use a configured read-only target for `consult` and `review`: workflow names do not enforce write safety. Workers edit only declared scope. Coordinator owns Git, anchors, gates, review, and handover; OpenMCP/workflows do not commit, reset, restore, stash, clean, integrate, or call back into Git.

## Summaries and listing

Summary fields are exactly `id, project_id, workflow, profile, state, context_key, attempts, access_mode, depends_on, waiting_on, waiting_reason, created_at, updated_at`. `job_list` returns every active job, newest ten terminal jobs, and integer `more_recent` (a count, not cursor). If a saved job is absent, call `job_wait(saved_id, timeout_s=0)` before concluding it is unknown. Absence never authorizes duplicate submission.

## Dependencies and admission

`depends_on` is immutable caller input; `access_mode`, `waiting_on`, and `waiting_reason` are derived. Failed/cancelled/interrupted dependencies cancel queued descendants; `job_cancel` returns their IDs as `cancelled_dependents`. Parent retry does not revive descendants. Verified readers may overlap within capacity; exclusive jobs are barriers; identical sessions serialize under reader/writer/session-fair admission. This does not permit concurrent gated Coordinator implementation/review in one root.

## Waiting, paging, and bounds

`job_wait` defaults to a 3600-second heartbeat; `timeout_s` ranges 0..3600 and `result_offset` is a nonnegative Unicode code-point offset, default 0. Wait sequentially, one call per job: no short hardcoded waits, polling, sleeps, or overlapping replacements. Repeat only after nonterminal output; after a dropped connection reuse the same ID. Timeout is normal, not failure.

Terminal pages pass `result.next_offset` as `result_offset` with `timeout_s=0` until null, concatenating every page. Paging applies only to terminal jobs; nonterminal text is empty and offset does not advance. Resolve/guide/submit/wait is four calls only for a terminal one-page standard cycle; resume, recovery, nonterminal waits, and paging add calls.

Every complete serialized response is below 30,000 characters and 9,000 UTF-8 bytes. Never silently omit metadata. On overflow after an applied mutation, state its actual outcome and preserve root job or project ID; never blindly resubmit.

## Errors

Expected failures are compact JSON with `isError: true` and `code`, `message`, `retryable`, `next_action`. Follow the action; retry only when marked retryable and the action allows it.

| Code | Safe next action |
|---|---|
| `unknown_project` | Resolve the supplied Git root with `project_resolve`. |
| `invalid_path` | Supply an existing absolute directory. |
| `alias_taken` | Choose a unique alias or omit it. |
| `unknown_job` | Reconcile using `job_list`; do not blindly duplicate. |
| `unknown_profile` | Call `task_guide`; select a listed profile. |
| `invalid_dependency` | Correct the named `depends_on` ID. |
| `dependency_failed` | Retry the dependency first, then this job. |
| `invalid_state` | Inspect using `job_wait`; use a new job if appropriate. |
| `config_invalid` | Report for correction in the dashboard. |
| `daemon_stopping` | Wait, then resolve the Git root again. |
| `invalid_request` | Correct arguments to the declared schema. |
| `response_too_large` | Inspect/reduce metadata; honor applied outcome/root ID; no blind retry. |
| `internal_error` | Retry once, then report request ID only. |

Internal errors expose no diagnostics, stack traces, provider, or execution details.

## Fresh and resumed sessions

Session key is project, context, workflow, and configured target key; target and native session identity stay private. First plan `implement` and `review` jobs use `fresh_session: true` with full role contracts. Later same-workflow jobs omit it and send only delta plus phase prompt path. Retry preserves the setting. Fresh jobs receive prompt verbatim without stored session/history; successful fresh jobs replace the stored session. Standard jobs resume it or receive bounded turn history when absent.
