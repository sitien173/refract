# OpenMCP v2 for Claude Code Design

**Status:** Confirmed 2026-10-07
**Consultation:** Read-only Gate 1 consultation succeeded through the `consult` profile; user decisions override it where noted.

## Purpose

Redesign the OpenMCP MCP surface to fit Claude Code as its only MCP client.
Make the coordinator cycle short, self-describing, and safe for long jobs.
Fold the confirmed job-dependency design into the same release.

This document specifies behavior; implementation has not started.

## Users and Success Criteria

The user is a Claude Code coordinator session driven by the superpowers-ccg skills.
Operators use the dashboard.

| ID | Criterion |
|---|---|
| a | One `job_wait` call covers a job up to 60 min from the main conversation or a subagent without a client timeout. After a daemon restart, the client issues a new `job_wait`. |
| b | Server instructions and every tool description are at most 2048 characters, with key facts first. |
| c | The full cycle resolve project, guide, submit, wait, read result needs no hidden URI and at most 4 calls. |
| d | No MCP output exposes target, backend, model, or provider identity. |
| e | Every error names the next action. |
| f | Every tool has accurate annotations. |
| g | Every MCP response is under 10k tokens. |

## Constraints and Non-Goals

### Confirmed constraints

- Clean-slate v2 with a hard cutover. No v1 tool or resource remains.
- OpenMCP and superpowers-ccg ship major versions in lockstep.
- Claude Code is the only MCP client; `anthropic/*` `_meta` keys are allowed.
- Existing project IDs, job IDs, and job rows stay readable through v2.
- `docs/plans/parallel-readers-job-dependencies/DESIGN.md` is adopted as written, except where this document overrides it.
- The dashboard is an operator tool and is exempt from criterion d.

### Verified client facts

Source: official Claude Code MCP and environment-variable documentation, fetched 2026-10-07, plus live observation.

- Tool search defers all MCP tools. Only tool names and server instructions load at session start.
- Descriptions and instructions are truncated at 2048 characters.
- HTTP calls have a 5 min idle timeout, reset only by a response or a progress notification.
- The wall-clock tool timeout defaults to about 28 h.
- Main-conversation calls longer than 2 min move to a background task. Subagent calls never move.
- Resource templates are invisible to `ListMcpResourcesTool`.
- Results over 50k characters are saved to a file; over 10k tokens trigger a warning.
- `isError` text is passed to the model as an error.

### Non-goals

- Channels.
- The MCP tasks primitive.
- Authentication or remote access; the daemon stays loopback-only.
- MCP Apps UI and elicitation.
- Any MCP resource.

## Chosen Approach

Tools only: seven tools, no resources, a long heartbeat `job_wait`, and JSON error payloads delivered as `isError` results.

Rejected alternatives:

- Tools plus resources: two read paths to maintain, and resource URIs stay hidden from Claude.
- One combined `job_run` call: duplicate-job risk when a timed-out call is repeated, and project-specific guidance cannot live in static instructions.

## Architecture and Data Flow

### Tool surface

| Tool | Parameters | Returns | Annotations |
|---|---|---|---|
| `project_resolve` | `path`, `alias=""` | `{project:{id, alias, path}}` | not read-only, not destructive, idempotent, closed-world |
| `task_guide` | `project_id` | `{workflows, profiles:{default, available}, guidance}` | read-only, closed-world |
| `job_submit` | `project_id`, `workflow`, `prompt`, `profile=""`, `context_key=""`, `fresh_session=false`, `depends_on=[]` | `{job: summary}` | not read-only, destructive, not idempotent, open-world |
| `job_wait` | `job_id`, `timeout_s=3600`, `result_offset=0` | `{job: summary, result:{text, error, next_offset}}` | read-only, closed-world |
| `job_list` | `project_id` | `{active:[summary], recent:[summary], more_recent:n}` | read-only, closed-world |
| `job_cancel` | `job_id` | `{job: summary, cancelled_dependents:[id]}` | not read-only, destructive, idempotent, closed-world |
| `job_retry` | `job_id` | `{job: summary}` | not read-only, destructive, not idempotent, open-world |

Job summary fields:

```text
id, project_id, workflow, profile, state, context_key, attempts,
access_mode, depends_on, waiting_on, waiting_reason, created_at, updated_at
```

Rules:

- `workflow` is an enum: `consult`, `implement`, `review`, `other`.
- `timeout_s` ranges from 0 to 3600.
- `recent` holds at most 10 terminal jobs; `more_recent` counts the rest.
- `depends_on` is caller input, immutable after submission.
- `access_mode`, `waiting_on`, and `waiting_reason` are server-derived.
- No MCP output contains `target_id`, `config_revision`, `resource_uri`, backend, or model fields.
- No tool sets `anthropic/alwaysLoad`; the skill names tools directly.

Removed from the MCP surface: `project_register`, `status`, the legacy `run()` facade, the subscription bus, `publish_job_resource`, and all five resource templates.
`status` is replaced as a health check by the first `project_resolve` call.

### Standard cycle

```text
project_resolve -> task_guide -> job_submit -> job_wait
```

### Project identity

1. `project_resolve` expands `~`, applies `Path.resolve()`, and requires an existing directory.
2. A stored root match returns the stored project and ignores `alias`.
3. No match creates the project. The default alias is the directory name, suffixed `-2`, `-3`, and so on when taken. An explicit taken alias raises `alias_taken`.
4. A unique constraint on `root` settles concurrent calls; the loser re-reads the existing row.
5. The server does not walk up to a Git root. The description tells the caller to pass the Git root.

### Waiting and heartbeats

1. `job_wait` sends progress immediately, then every 30 s, until the job is terminal or `timeout_s` elapses.
2. Each progress message carries `state` and `waiting_reason`.
3. The heartbeat interval is injectable for tests.
4. A timeout is a normal result: current summary plus `next_action: "Call job_wait again with the same job_id."`
5. A daemon restart drops the call. The job persists, and instructions tell Claude to call `job_wait` again.

The SDK sends progress only when the request carries a progress token; see `_streamable_http_modern.py:114` in `mcp` 2.0.0.
Phase 0 must confirm Claude Code sends one. See Risks.

### Result paging and response bounds

- 24,000 Unicode code points is the maximum candidate result page, not a fixed page size. Shrink the page against the complete serialized tool result so escaping and non-ASCII content cannot exceed the response budget.
- Use one compact JSON text content with structured output disabled. No duplicate structured copy is emitted.
- Every complete tool result is under 30,000 serialized characters and under a conservative 9,000-byte UTF-8 budget. This leaves headroom below the 10k-token client warning without adding a tokenizer dependency.
- `result.next_offset` is `null` when the text is complete, otherwise the next Unicode code-point offset. Advance by the actual page length, preserving every character.
- `job_wait(job_id, timeout_s=0, result_offset=n)` returns that page immediately.
- Paging applies only to terminal jobs; non-terminal jobs return empty `text` and do not advance the offset.
- Keep the seven tool signatures unchanged. Non-pageable metadata that cannot fit returns `response_too_large` with `isError` and an actionable `next_action`, never a silently truncated success. This includes active lists, guidance, dependency and cancellation arrays, and summary fields.
- If a mutating operation has already applied before an overflow is detected, the error must state that outcome and retain the root job or project ID in its message or next action. Never imply that blind resubmission is safe.

The user approved adaptive result pages and explicit overflow errors on the Phase 4 approval question. List and guidance pagination are not part of this release.

### Dependencies

The confirmed dependency design governs admission, ordering, fairness, persistence, migration, retry, and cascade cancellation.
This document overrides it as follows:

| Confirmed dependency design | v2 |
|---|---|
| Fields exposed through job resources | Fields exposed in the job summary returned by every job tool |
| Notify subscribers for cancelled dependents | Release completion waiters only |
| Reject dependent retry with a dependency-specific explanation | Error code `dependency_failed` |
| `max_project_readers` daemon setting, default 1 | Unchanged; dashboard shows it under v2 names |

`waiting_reason` is plain text, for example `waiting on dependency <id>` or `waiting for project write slot`.
The dependency design is marked merged into this design and gets no separate plan.

### Server instructions

Set `instructions` on `MCPServer`, at most 2048 characters:

```text
OpenMCP runs durable coding jobs (consult, implement, review, other) on external
agents for a local project. Jobs persist across client disconnects and daemon restarts.

Standard cycle, 4 calls:
1. project_resolve(path=<Git root>) -> project.id. Idempotent; once per session.
2. task_guide(project_id) -> choose workflow and profile from recommendations.
3. job_submit(project_id, workflow, prompt, ...) -> job.id. The prompt must be
   self-contained; workers do not see this conversation.
4. job_wait(job_id) -> blocks up to 3600 s with progress every 30 s. Read result.text.
   If result.next_offset is not null, call job_wait(job_id, timeout_s=0,
   result_offset=<next_offset>) for the next page.

Rules:
- job_wait returning a non-terminal state is not an error. Call job_wait again.
- A dropped connection may mean the daemon restarted. Jobs persist; call job_wait again.
- Use depends_on=[job ids] to chain jobs without waiting between submits.
  A failed dependency cancels its dependents.
- Reuse context_key to continue a worker session; fresh_session=true starts over.
- On session resume, call job_list(project_id) and reconcile active jobs before
  submitting new ones.
- Errors are JSON with code, message, next_action. Follow next_action.
```

Set the server title to `OpenMCP job queue`.

### Tool descriptions

- First sentence: what the tool does and when to use it.
- Then parameter meaning, return shape, and the error codes the tool can raise.
- Target at most 600 characters each; hard limit 2048.
- Every parameter has `Field(description=...)`; limits live in the schema.
- Every tool has a human-readable `title` annotation.

### Dashboard

- Job payloads add `access_mode`, `depends_on`, `waiting_on`, and `waiting_reason`.
- The project job list uses the `active` and `recent` shape of `job_list`.
- Settings expose `max_project_readers`.
- Keep one canonical route per resource and update `web/src` to match. Candidate duplicate pairs:
  - `/dashboard/api/status` and `/dashboard/api/overview`
  - `/dashboard/api/configuration` and `/dashboard/api/config`
  - `/dashboard/api/projects/{project_id}/profile-overrides` and `/dashboard/api/projects/{project_id}/configuration/profiles`
- The dashboard keeps `target_id`, execution plans, and provider detail.

### superpowers-ccg

Repository: `/home/ngosi/projects/superpowers-ccg`.

- Rewrite `skills/coordinating-multi-model-work/references/tool-contract.md` for the seven tools and no resources.
- In `skills/coordinating-multi-model-work/SKILL.md`:
  - the `status` call becomes `project_resolve`;
  - the `openmcp://projects` read and conditional registration become `project_resolve`;
  - reconciliation reads `job_list`;
  - profile and workflow validation reads `task_guide`;
  - waiting is one `job_wait`, repeated only when the result is non-terminal.
- Document `depends_on` in the contract. Coordinator behavior otherwise stays unchanged.

## Errors and Edge Cases

### Error delivery

All expected failures raise `OpenMCPError(code, message, next_action, retryable)`.
Its string form is one compact JSON line.
The SDK wraps it as `Error executing tool <name>: <json>` with `isError` set; see `tools/base.py:181` and `server.py:424` in `mcp` 2.0.0.
`_logged_request` converts any other exception into `internal_error` after logging it with the request ID.
No stack trace or provider detail reaches the client.

### Error codes

| Code | Trigger | `next_action` |
|---|---|---|
| `unknown_project` | Unregistered `project_id` | Call `project_resolve` with the Git root |
| `invalid_path` | Path missing or not a directory | Pass an existing absolute directory |
| `alias_taken` | Explicit `alias` already used by another project | Pass a unique alias or omit it |
| `unknown_job` | `job_id` not found | Call `job_list` for the project |
| `unknown_profile` | Profile not in the project catalog | Call `task_guide` and use a listed profile |
| `invalid_dependency` | Unknown, duplicate, or other-project dependency ID | Fix `depends_on`; message names the ID |
| `dependency_failed` | Dependent retry while a dependency is terminally unsuccessful | Retry dependency `<id>` first, then this job |
| `invalid_state` | `job_retry` on a job that is not failed, cancelled, or interrupted | Message names the state; call `job_wait` or submit a new job |
| `config_invalid` | Daemon configuration fails to load | Fix it in the dashboard; message names the source path |
| `daemon_stopping` | Daemon shutting down | Wait, then call `project_resolve` again |
| `invalid_request` | Malformed, missing, or out-of-range tool arguments | Correct the arguments using the tool schema and call the tool again |
| `response_too_large` | Non-pageable metadata exceeds the response budget | Use the dashboard to inspect or reduce the oversized data before retrying; do not blindly repeat an already-applied mutation |
| `internal_error` | Any unexpected exception | Retry once, then report the request ID |

The user approved `invalid_request` and `response_too_large` in the Phase 4 approval question. Schema validation failures are model-visible JSON errors, not protocol-only exceptions. Expected errors use the SDK ToolError seam; request middleware normalizes only recognizable OpenMCP JSON payloads from SDK prefixes and covers pre-handler validation. Cancellation propagates unchanged.

### Non-errors

- `job_cancel` on a terminal job returns its unchanged summary.
- `job_wait` timeout returns a normal result.
- Submission against an unsuccessful terminal dependency creates a cancelled job, per the dependency design.

### Open observation

A live `job_submit` with an unknown `project_id` showed only `Error executing tool job_submit`.
The code path above should include the message. The cause is unverified; Phase 0 checks it from Claude Code.

## Migration

- Database: add `access_mode` and the `job_dependencies` table. Existing jobs become `exclusive` with no dependencies.
- Existing project IDs and job rows remain valid; no project migration is needed.
- Remove `run()`, `project_register`, `status`, resource templates, the subscription bus, `publish_job_resource`, `resource_uri`, and `JOB_RESOURCE_URI_TEMPLATE`.
- Remove `backend_runner` and similar helpers only if nothing else imports them.
- Bump OpenMCP and superpowers-ccg major versions together.
- Release notes: update both, then restart the daemon. Mixed versions fail with unknown-tool errors.
- Update the task-guide line "submit dependent jobs sequentially" only if the text ships in this repository.

## Testing

These are acceptance requirements, not executed results.

| Area | Required evidence |
|---|---|
| Tool list | Names, titles, annotations, parameter descriptions, enum and range limits |
| Lengths | Instructions and every description at most 2048 characters; instructions name every tool; no description mentions a resource URI |
| Cycle | Resolve, guide, submit, wait completes in 4 calls through an in-process MCP client |
| Identity | Recursive scan finds no `target_id`, `backend`, `model`, `resource_uri`, or `config_revision` in any tool output |
| Resolve | Idempotent for the same path, symlinked paths, and concurrent calls |
| Errors | Each code arrives with `isError` and parseable JSON containing `next_action` |
| Heartbeat | Progress emitted at the injected interval until terminal or timeout |
| Paging | Offsets cover the full text; every response under 30,000 characters |
| Dependencies | The full acceptance table of the dependency design |
| Dashboard | Existing web test suite passes against renamed routes and new fields |

Live acceptance in Claude Code:

- Phase 0 progress-token check.
- A `job_wait` of at least 6 min from the main conversation and from a subagent.
- One invalid call shows the full error JSON.

Proposed phases, settled in the plan: 0 spike, 1 dependency scheduler and migration, 2 MCP v2 surface, 3 dashboard, 4 superpowers-ccg, 5 live acceptance and release.

## Risks and Open Questions

### Risks

- If Claude Code sends no progress token, heartbeats are dropped and waits over 5 min fail. Fallback: cap `timeout_s` at 240 and rely on repeat calls. That breaks criterion a, so the user decides before planning continues.
- Lockstep cutover leaves a window where mixed versions fail.
- Dependency-design risks carry over, including adapter read-only verification.

### Open questions

- Which candidate dashboard routes are pure aliases. The plan verifies against `web/src`.
- Whether the task-guide text ships in this repository.
- Why the observed error lost its message.

### Consultation and source evidence

The consultation recommended tools only, a long heartbeat wait, `project_resolve`, seven tools, and dropping `status`.
User decisions and verification overrode it on:

- dashboard scope: renamed with v2 vocabulary instead of left as is;
- error delivery: `isError` results instead of `ok:false` success payloads;
- dependency errors: failed dependencies create cancelled jobs and cycles cannot occur, per the confirmed dependency design.

Clean baseline anchor:

```text
refs/plans/mcp-v2-claude-code/base
```
