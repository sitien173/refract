# OpenMCP workflow reference

OpenMCP supports only built-in workflows. Project custom workflow files are not
loaded.

| Workflow | Behavior | Submission fields |
| --- | --- | --- |
| `implement` | Commits successful tracked changes directly. | `prompt`, optional `commit_message` |
| `review` | Must leave the repository unchanged. | `prompt` |
| `consult` | Must leave the repository unchanged. | `prompt` |

Use an optional `profile` to select configured targets and an optional
`context_key` for conversational continuity.

```json
{
  "project_id": "project-id",
  "workflow": "review",
  "prompt": "Review the current implementation for correctness and regressions.",
  "context_key": "feature/review",
  "profile": "quality"
}
```

Submit dependent work sequentially. A review sees implementation changes after
the implementation has committed. Add review findings to a later implementation
prompt when a fix is needed.
