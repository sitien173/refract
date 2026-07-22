---
name: openmcp-orchestrate
description: Orchestrate durable Git project work through OpenMCP MCP tools. Use for daemon checks, project registration, task guidance, workflow and profile selection, job monitoring, retries, and cancellation.
---

# OpenMCP orchestration

Read [references/tool-contract.md](references/tool-contract.md) before the
first OpenMCP call in a session.

## Guardrails

- Use real OpenMCP tools. Never simulate successful jobs.
- Require a clean repository before registration.
- Never commit, stash, reset, or delete user changes.
- Do not edit a registered repository while a job runs.
- Select semantic workflows and profiles, not providers or target IDs.
- Never send credentials or secret values.

## Workflow

1. Call `status`. Require `status="running"`.
2. Read `openmcp://projects`. Register a missing clean root.
3. Call `task_guide` for the complete task.
4. Submit one built-in workflow with named fields:

```json
{
  "project_id": "project-uuid",
  "workflow": "implement",
  "prompt": "Implement the approved repository change.",
  "commit_message": "feat: implement approved change",
  "context_key": "change/implement",
  "profile": "quality"
}
```

5. Call `job_wait` with a finite timeout. Repeat only while queued or running.
6. Inspect `result.text`, `result.commit`, and errors.
7. Use `job_retry` once for a failed, cancelled, or interrupted job when useful.

`implement` commits successful changes directly to the registered branch.
`review` and `consult` must leave the repository unchanged. Jobs for one
project run in submission order. Jobs for different projects may run together.

For higher-risk work, submit `consult`, then `implement`, then `review` as
separate jobs. The review examines the current repository after implementation
has committed. A fix is a new `implement` job with review findings in its
prompt. Context keys carry optional conversation continuity.

## Handoff

Report workflow, profile, job ID, terminal state, commit, and verification.
