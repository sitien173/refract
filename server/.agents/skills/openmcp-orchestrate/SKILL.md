---
name: openmcp-orchestrate
description: Orchestrate durable Git project work through OpenMCP MCP tools. Use for daemon checks, configuration reloads, integration validation, project registration, task guidance, workflow and profile selection, job monitoring, implementation/review chains, retries, cancellation, integration, or permitted local overlays.
---

# OpenMCP orchestration

Use OpenMCP as the durable project coordinator. Keep provider identities and
temporary worktrees outside user-facing instructions.

Read [references/tool-contract.md](references/tool-contract.md) before the first
OpenMCP call in a session.

## Guardrails

- Use real OpenMCP tools; never simulate successful jobs.
- Resolve the Git root and require a clean repository before submission.
- Never commit, stash, reset, or delete dirty user changes.
- Keep the registered repository unchanged while jobs run.
- Avoid parallel implementation jobs that both require integration.
- Select semantic workflows and profiles, not providers or target IDs.
- Never send credentials or secret values.
- Treat integration conflicts as blockers.

## Orchestration workflow

### 1. Check the daemon and project

1. Confirm OpenMCP tools are available.
2. Call `status` and require `status="running"`.
3. Read `openmcp://projects` when resource access exists.
4. Match by resolved Git root.
5. Call `project_register` only when no match exists.
6. Call `doctor` when integration validation is requested.

If tools are unavailable, report the default endpoint
`http://127.0.0.1:8765/mcp` and stop. Do not silently replace OpenMCP with direct
execution. If the repository is dirty, stop and report affected paths.

### Configuration reloads

Call `reload` after changing global targets, profiles, or target arguments. It
validates and activates them for subsequent submissions without interrupting
running jobs. Inspect `success` and `restart_required`.

Host, port, worker, history, home, and logging changes require process restart.
Project profile overrides and task guides reload when used.

### 2. Consult task guidance

Call `task_guide` with the complete task and optional project identifier. Match
use cases to a `workflow` and optional `profile`:

- `implement`: may change files and produce a commit.
- `review`: read-only code-quality review.
- `consult`: read-only inspection, analysis, or advice.

Only these built-ins are submit-able. For multi-step work, create a parent job
chain rather than a custom workflow file.

### 3. Submit precisely

Call `job_submit` with:

- `project_id`
- one built-in `workflow`
- `inputs.prompt` defining outcome, scope, constraints, and validation
- `inputs.commit_message` for `implement` when appropriate
- a stable topic-specific `context_key`
- `parent_job_id` for dependent work
- the guide's `profile` when present

Omit `profile` only to use the configured default. Prefer context keys such as
`topic/phase/workflow`. Split mixed work into dependent jobs and unrelated work
into separate jobs.

### 4. Wait without busy polling

Call `job_wait` with a finite timeout, normally 30 seconds. Repeat only while
state remains `queued` or `running`. Request stage outputs only for diagnosis.
Do not modify the registered repository while waiting.

### 5. Evaluate results

- `succeeded`: inspect `result.text`, `result.commit`, and stages.
- `failed`: inspect the error before one targeted retry.
- `interrupted`: retry only when resumption remains useful.
- `cancelled`: stop unless the user requests resumption.
- `integration_conflict`: inspect and report repository state.

Use `job_retry` from the earliest invalid stage. Never create retry loops.

### 6. Review and integrate

For higher-risk changes:

```text
implement -> review -> implement fix
```

Set each dependent job's `parent_job_id`. Use a review-focused profile only
when configured. Integrate the latest approved implementation; if review passes
without a fix, integrate the reviewed implementation.

Call `job_integrate` only when the implementation succeeded, required review
passed, and the original repository remains clean and unchanged. Never integrate
review or consultation jobs. Verify repository status afterward.

## Local overlays

Use ignored `.openmcp.local.toml` only when jobs need selected ignored files.
Prefer exact paths, then narrow includes and explicit excludes. List only
permitted workflows. Never expose secrets. Overlay changes apply during
`job_integrate` and hash conflicts protect concurrent local edits.

## Related skills

- Use `openmcp-config` to add targets, profiles, overlays, or task guidance.
- Use `openmcp-workflows` to select built-ins and design safe parent job chains.

## Handoff

Report workflow, profile, job ID, terminal state, commit, verification outcome,
and any conflict or retained artifact.
