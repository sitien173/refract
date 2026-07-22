# OpenMCP tool contract

Default endpoint: `http://127.0.0.1:8765/mcp`.

| Tool | Required inputs | Optional inputs | Purpose |
| --- | --- | --- | --- |
| `status` | | | Return scheduler health and queue counts. |
| `reload` | | | Reload global targets and profiles. |
| `doctor` | `path` | | Return read-only integration checks. |
| `project_register` | `path` | `alias` | Register a clean Git root. |
| `task_guide` | `task` | `project_id` | Load workflow/profile guidance. |
| `job_submit` | `project_id`, `workflow`, `prompt` | `commit_message`, `context_key`, `profile` | Queue durable work. |
| `job_wait` | `job_id` | `timeout_s` | Wait for completion or timeout. |
| `job_cancel` | `job_id` | | Cancel queued or running work. |
| `job_retry` | `job_id` | | Retry failed, cancelled, or interrupted work. |

## Built-in workflows

| Workflow | Behavior |
| --- | --- |
| `implement` | Runs once and commits successful tracked changes immediately. |
| `review` | Runs once and must leave the repository unchanged. |
| `consult` | Runs once and must leave the repository unchanged. |

Use named submission fields:

```json
{
  "project_id": "project-id",
  "workflow": "implement",
  "prompt": "Implement the requested change and run focused tests.",
  "commit_message": "feat: implement requested change",
  "context_key": "feature/implement",
  "profile": "quality"
}
```

Job states are `queued`, `running`, `succeeded`, `failed`, `cancelled`, and
`interrupted`. Successful jobs expose `result.text` and `result.commit`.
