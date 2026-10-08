# OpenMCP v2 Tool Contract

Default endpoint: `http://127.0.0.1:8765/mcp`; set `OPENMCP_URL` before Claude Code starts.

## Seven tools

| Tool | Required | Optional | Purpose |
|---|---|---|---|
| `project_resolve` | `path` | — | Resolve canonical Git root. |
| `task_guide` | `project_id` | — | Public workflow/profile names and guidance. |
| `job_submit` | `project_id`, `workflow`, `prompt` | `context_key`, `profile`, `fresh_session` (false), `depends_on` | Submit immutable job. |
| `job_wait` | `job_id` | `timeout_s` (3600), `result_offset` | Wait/page result. |
| `job_list` | `project_id` | — | List jobs. |
| `job_cancel` | `job_id` | — | Cancel job and queued descendants. |
| `job_retry` | `job_id` | — | Retry failed/cancelled/interrupted job. |

Match namespaced tool suffixes. Do not invent parameters.

## Guidance and routing

Valid workflows: `consult`, `implement`, `other`, `review`. Profiles may be
partial. Guidance exposes public names/prose only. Validate public names, not
invented configuration, target, or capability fields. Unsupported mappings are
resolved through actual guidance/errors; never substitute an unapproved route.
`task_guide` takes `project_id` only; the full phase request belongs in
self-contained `job_submit.prompt`.

## Summaries and reconciliation

Summary fields: `id, project_id, workflow, profile, state, context_key, attempts,
access_mode, depends_on, waiting_on, waiting_reason, created_at, updated_at`.
`job_list` returns every active job, newest ten terminal jobs, integer
`more_recent` (a count, not cursor). If a saved job is absent, call
`job_wait(saved_id, timeout_s=0)` before calling it unknown. Absence never
permits duplicate submission.

## Dependencies and admission

Jobs run in the registered Git root; OpenMCP neither owns Git nor checks
cleanliness. `depends_on` is an immutable ID list; admission/waiting metadata is
derived. Failed, cancelled, or interrupted dependencies cancel queued
descendants; IDs appear in `cancelled_dependents`. Parent retry does not revive
them. Verified readers may overlap within capacity; exclusive jobs are barriers;
identical sessions serialize under reader/writer/session-fair admission. This
does not permit concurrent Coordinator implementation/review in one root:
gated submissions remain sequential.

## Waiting and results

Start one sequential `job_wait` per job with the default 3600-second heartbeat.
No short timeout, polling, sleep, or overlapping replacement wait. Repeat only
after nonterminal output; after disconnect use the same ID. Timeout is normal,
not failure. Terminal pages pass `result.next_offset` as `result_offset` with
`timeout_s=0` until null; reconstruct every page in order. Result is in the wait
response. Resolve/guide/submit/wait is four calls only for a terminal one-page
standard cycle; resume, recovery, nonterminal replacement waits and paging add
calls.

Complete wire responses are below 30000 serialized characters and 9000 UTF-8
bytes; metadata is never silently truncated. After oversized metadata following
an applied mutation, follow its outcome and root job ID, not blind resubmission.

## Errors

Expected errors are compact model-visible JSON: `code`, `message`, `retryable`,
`next_action`. Approved codes: `INVALID_ARGUMENT`, `PROJECT_NOT_FOUND`,
`PROJECT_PATH_MISMATCH`, `WORKFLOW_NOT_FOUND`, `PROFILE_NOT_FOUND`,
`ROUTE_NOT_FOUND`, `JOB_NOT_FOUND`, `JOB_NOT_RETRYABLE`,
`JOB_NOT_CANCELLABLE`, `DEPENDENCY_NOT_FOUND`, `DEPENDENCY_CYCLE`,
`DEPENDENCY_FAILED`, `CAPACITY_EXCEEDED`. Follow `next_action`; retry only when
allowed. Internal errors expose request ID only, never diagnostics.

## Fresh/resumed sessions and ownership

Session key is project/context/workflow/session identity. First plan implement
and review jobs use `fresh_session: true` with full role contracts; later
same-workflow jobs omit it and send delta plus phase prompt. Retry retains the
setting. Fresh jobs receive prompt verbatim without stored session/history and
successful fresh jobs replace stored session. Standard jobs resume it or receive
bounded turn history if absent.

Coordinator alone owns Git, anchors, gates, review, handover. Workers edit only
declared paths; OpenMCP/workflows never commit, reset, or restore. Retry reruns
the immutable job without resetting files: reconcile first. New submission is
only for changed prompts, after reconciliation.
