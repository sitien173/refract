---
name: openmcp-orchestrate
description: Orchestrate durable Git project work through OpenMCP MCP tools. Use when an agent needs to initialize or register a project, route work, choose role workflows or routing profiles, submit or monitor jobs, chain implementation and review jobs, retry or cancel jobs, integrate successful writes, or expose permitted ignored development files through local overlays.
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
- Avoid parallel write jobs requiring integration.
- Use logical workflows and routing profiles, not providers.
- Never send credentials, private keys, or secret values.
- Treat integration conflicts as blockers. Never reset user branches.

## Orchestration workflow

### 1. Discover the project

1. Confirm the OpenMCP tools are available.
2. Read `openmcp://projects` when resource access exists.
3. Match projects using their resolved Git root.
4. Call `project_register` only when no match exists.
5. Use `project_init` only when project configuration is requested.
6. Commit initialized configuration before submitting jobs.

If tools remain unavailable, report the default loopback endpoint and stop.
Never silently replace OpenMCP with direct execution.

If the repository is dirty, stop and report affected paths. Let the user decide
how to preserve them.

### 2. Route the task

Call `task_route` with the complete task and project identifier. Apply its
project-specific routing template. Select the smallest fitting workflow:

- Use `forge-read` for non-UI inspection or analysis.
- Use `forge-write` for non-UI implementation.
- Use `canvas-read` for UI inspection or design review.
- Use `canvas-write` for UI implementation.
- Use `sage-read` for strategic consultation.
- Use `sentinel-read` for independent review.
- Use custom workflows only for distinct execution shapes.

Split mixed work into dependent jobs. Keep unrelated tasks separate.

### 3. Submit precisely

Call `job_submit` with:

- A prompt defining outcome, scope, constraints, and validation.
- A concise commit message for write workflows.
- A stable topic-specific `context_key`.
- A `parent_job_id` for dependent review or fix work.
- A `routing_profile` only when policy requires one.

Prefer context keys shaped like `topic/phase/role`. Reuse them only when
continuity helps. Use the project default routing profile otherwise.

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

For higher-risk writes, submit `sentinel-read` with the write job as parent.
Submit fixes as a write child of that review. Integrate the latest approved
write job. If the chain ends in a read review, integrate its write ancestor.

Call `job_integrate` only when:

- The user requested repository changes.
- The write job succeeded.
- Required review passed.
- The original repository remains clean and unchanged.

Never integrate read-only jobs. Verify repository status after integration.

## Local overlays

Use overlays only when jobs need ignored development files. Keep
`.openmcp.local.toml` ignored. Prefer exact paths, then narrow includes and
explicit excludes. List only permitted workflows.

Overlay changes apply during `job_integrate`, outside Git history. Hash conflicts
protect concurrent local edits. Overlay snapshots remain under OpenMCP run
storage. Never expose secrets through overlays.

## Handoff

Report the workflow, job identifier, terminal state, integrated commit, and
verification outcome. Report conflicts or retained artifacts when relevant.
