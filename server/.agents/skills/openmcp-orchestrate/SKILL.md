---
name: openmcp-orchestrate
description: Orchestrate durable Git project work through OpenMCP MCP tools. Use when an agent needs daemon status or configuration reloads, integration validation, project registration, task routing, semantic workflow selection, job monitoring, implementation and review chains, retries, cancellation, integration, or permitted local overlays.
---

# OpenMCP Orchestration

Use OpenMCP as the durable project coordinator. Keep provider identities,
temporary worktrees, and internal routing outside user-facing instructions.

Read [references/tool-contract.md](references/tool-contract.md) before the first
OpenMCP call in a session. Re-read only relevant sections after errors.

## Guardrails

- Use actual OpenMCP MCP tools. Never simulate successful jobs.
- Resolve the Git root before registering projects.
- Require a clean repository before submission.
- Preserve dirty user changes. Never commit, stash, or delete them.
- Keep the registered repository unchanged while jobs run.
- Avoid parallel implementation jobs requiring integration.
- Use semantic workflows and routing profiles, not providers.
- Never send credentials, private keys, or secret values.
- Treat integration conflicts as blockers. Never reset user branches.

## Orchestration workflow

### 1. Check the daemon and discover the project

1. Confirm the OpenMCP tools are available.
2. Call `status` and require `status="running"` before orchestration.
3. Read `openmcp://projects` when resource access exists.
4. Match projects using their resolved Git root.
5. Call `project_register` only when no match exists.
6. Call `doctor` when project integration validation is requested.

`status` is a read-only scheduler snapshot. `doctor` returns project integration
checks and never mutates files. Prefer project-level agent behavior over global
behavior. The MCP connection may remain global. Keep daemon settings and targets
in global OpenMCP configuration.

If tools remain unavailable or `status` cannot be called, report the default
loopback endpoint and stop. Never silently replace OpenMCP with direct
execution.

If the repository is dirty, stop and report affected paths. Let the user decide
how to preserve them.

### Daemon configuration reloads

Call `reload` after changing global targets, routes, routing profiles, or target
arguments when the user wants immediate validation and activation. It reloads
those settings for subsequent submissions without interrupting running jobs.
Inspect `success` and `restart_required`; do not claim full activation when the
latter is non-empty. Host, port, worker, history, home, and logging changes still
require a process restart. An invalid configuration makes `reload` fail and
leaves the previous catalog active.

Do not call `reload` for project route/profile overrides or task-route templates;
they reload when used.

### 2. Route the task

Call `task_route` with the complete task and project identifier. Apply its
project-specific routing template. Match each use case to a `workflow` and,
when present, a `routing_profile`. Do not treat agent labels or route IDs as
submission profiles. Select the workflow by intent:

- Use `implement` for tasks that may change files.
- Use `review` for code-quality review.
- Use `consult` for inspection, analysis, or consultation.
- Use custom workflows only for multi-stage execution.

Each built-in resolves through its matching logical role. Every routing profile
must map `implement`, `review`, and `consult` onto routes. Pass the matched
`routing_profile` to `job_submit`; if the template omits it, use the project or
global default profile.

Split mixed work into dependent jobs. Keep unrelated tasks separate.

### 3. Submit precisely

Call `job_submit` with:

- A prompt defining outcome, scope, constraints, and validation.
- A concise commit message for `implement`.
- A stable topic-specific `context_key`.
- A `parent_job_id` for dependent review or fix work.
- The task-route entry's `routing_profile` when it specifies one.

Prefer context keys shaped like `topic/phase/role`. Reuse them only when
continuity helps. Omit `routing_profile` only when the matching entry does not
specify one, allowing OpenMCP to use the configured default.

### 4. Wait without busy polling

Call `job_wait` with a finite timeout. Use 30 seconds by default. Repeat only
while the returned state remains `queued` or `running`. Request stage outputs
only for diagnosis. Use job events when failure context remains unclear.

Do not modify the registered repository during this period.

### 5. Evaluate results

- On `succeeded`, inspect `result.text`, `result.commit`, and stages.
- On `failed`, inspect errors before considering one targeted retry.
- On `interrupted`, retry only when resumption remains useful.
- On `cancelled`, stop unless the user requests resumption.
- On `integration_conflict`, inspect repository state and report it.

Use `job_retry` from the earliest invalid stage. Never create retry loops.

### 6. Review and integrate

For higher-risk changes, submit `review` with the implementation job as parent.
Use a reviewer-specific routing profile only when configured. Submit fixes as
an `implement` child of that review. Integrate the latest approved
implementation. If the chain ends in review, integrate its implementation
ancestor.

Call `job_integrate` only when:

- The user requested repository changes.
- The implementation job succeeded.
- Required review passed.
- The original repository remains clean and unchanged.

Never integrate review or consultation jobs. Verify repository status afterward.

## Local overlays

Use overlays only when jobs need ignored development files. Keep
`.openmcp.local.toml` ignored. Prefer exact paths, then narrow includes and
explicit excludes. List only permitted workflows.

Use `workflows = ["implement"]` for built-in implementation overlays.

Overlay changes apply during `job_integrate`, outside Git history. Hash conflicts
protect concurrent local edits. Overlay snapshots remain under OpenMCP run
storage. Never expose secrets through overlays.

## Related skills

Orchestration drives existing configuration. When the task actually needs new
configuration or a new pipeline shape, hand off:

- Use `openmcp-config` to add a target, route, routing profile, overlay, or
  task-route template.
- Use `openmcp-workflows` to author a custom multi-stage `.openmcp/workflows`
  DAG. Author one only when built-ins cannot express the work as a single step.

## Handoff

Report the workflow, job identifier, terminal state, commit, and
verification outcome. Report conflicts or retained artifacts when relevant.
