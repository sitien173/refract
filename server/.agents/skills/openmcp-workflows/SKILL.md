---
name: openmcp-workflows
description: Select OpenMCP built-in workflows. Use when deciding between implement, review, and consult or replacing requests for unsupported custom workflow YAML.
---

# OpenMCP workflows

OpenMCP exposes exactly three workflows:

- `implement` changes files directly in the registered repository and commits success.
- `review` performs code review and must not change the repository.
- `consult` performs analysis or advice and must not change the repository.

Project-defined workflow files are not loaded. Do not author custom workflows.
Read [references/workflow-reference.md](references/workflow-reference.md).

## Selection

| Intent | Workflow |
| --- | --- |
| Modify repository files | `implement` |
| Review code or an implementation | `review` |
| Inspect, plan, explain, or advise | `consult` |

Use sequential submissions for multi-step work. For example:

```text
consult -> implement -> review
```

Each job sees the current repository when it starts. Put findings from a prior
job into the next job prompt when needed. Use stable `context_key` values only
when conversation continuity helps.

`commit_message` is optional and valid only for `implement`. Retry the whole job
with `job_retry` after failed, cancelled, or interrupted work. Do not create
custom workflow YAML.
