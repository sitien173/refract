# OpenMCP workflow reference

OpenMCP supports only built-in workflows. Project custom workflow files are not
loaded.

## Built-ins

| Workflow | Mode | Inputs | Result |
| --- | --- | --- | --- |
| `implement` | Write | required `prompt`, optional `commit_message` | Text and optional commit |
| `review` | Read | required `prompt` | Review text |
| `consult` | Read | required `prompt` | Analysis text |

The former `read` and `write` workflow names are unsupported. Select `review` or
`consult` according to intent, and `implement` for changes.

## Selection

Callers choose a workflow and optional profile:

```json
{
  "project_id": "project-id",
  "workflow": "review",
  "profile": "quality",
  "inputs": {
    "prompt": "Review the implementation for correctness and regressions."
  },
  "context_key": "feature/review",
  "parent_job_id": "implementation-job-id"
}
```

Profiles map workflows directly to targets. Provider and target names are not
submission parameters.

## Write behavior

`implement` runs in an isolated primary worktree. A successful write may create
a commit, but the registered project is unchanged until `job_integrate`.

Use a concise `commit_message` when the job should commit:

```json
{
  "prompt": "Add empty-name validation and run focused tests.",
  "commit_message": "feat: validate empty names"
}
```

## Read behavior

`review` and `consult` run read-only in disposable worktrees. They do not require
integration. Their final text is returned in `result.text`.

## Parent job chains

`parent_job_id` links dependent submissions. The child starts from the parent's
result commit while preserving the chain's original integration base.

Recommended patterns:

```text
implement -> review
implement -> review -> implement fix
```

A parent must be a successful job with a commit. When a read-only job cannot be
a commit anchor, place its findings explicitly in the next prompt while using
the latest implementation as the Git parent.

## Context keys

`context_key` identifies conversational continuity independently from Git
parentage. Use topic-specific keys and reuse only when continuity helps.

```text
feature/implement
feature/review
feature/fix
```

## Retry

Use `job_retry` only for failed, cancelled, or interrupted jobs. Select
`from_stage` only when diagnosing persisted stage state; built-ins normally have
a single `execute` stage. Avoid automatic retry loops.

## Integration

Integrate only a successful `implement` job when:

- requested changes are complete,
- required review passed,
- the registered repository remains clean and unchanged.

If a reviewed implementation needs no fix, integrate that implementation. If a
fix job follows review, integrate the successful fix. Never integrate `review`
or `consult` jobs.

## Unsupported custom workflows

Do not create `.openmcp/workflows/*.yaml`. Translate multi-step requests into a
sequence of built-in jobs with explicit prompts and parent relationships.
