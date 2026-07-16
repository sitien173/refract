# OpenMCP tool contract

The default streamable HTTP endpoint is `http://127.0.0.1:8765/mcp`.

## Tools

| Tool | Required inputs | Optional inputs | Purpose |
| --- | --- | --- | --- |
| `project_init` | `path` | | Create missing project configuration. |
| `project_register` | `path` | `alias` | Register a clean Git root. |
| `task_route` | `task` | `project_id` | Load effective routing guidance. |
| `job_submit` | `project_id`, `workflow`, `inputs` | `context_key`, `parent_job_id`, `routing_profile` | Queue durable work. |
| `job_wait` | `job_id` | `timeout_s`, `include_stage_outputs` | Wait for completion or timeout. |
| `job_cancel` | `job_id` | | Cancel queued or running work. |
| `job_retry` | `job_id` | `from_stage` | Retry failed or interrupted work. |
| `job_integrate` | `job_id` | | Fast-forward a successful write. |

Tool names may be client-namespaced. Match their OpenMCP suffixes.

## Built-in workflows

| Domain | Read | Write |
| --- | --- | --- |
| Non-UI engineering | `forge-read` | `forge-write` |
| UI engineering | `canvas-read` | `canvas-write` |
| Strategy | `sage-read` | |
| Independent review | `sentinel-read` | |

`single-read` and `single-write` remain compatibility workflows. Prefer role
workflows. Project workflows live under `.openmcp/workflows/*.yaml`.

Common write inputs:

```json
{
  "prompt": "Implement the requested change and run focused tests.",
  "commit_message": "feat: implement requested change"
}
```

## Resources

- `openmcp://projects`
- `openmcp://projects/{project_id}`
- `openmcp://projects/{project_id}/jobs`
- `openmcp://jobs/{job_id}`
- `openmcp://jobs/{job_id}/events`
- `openmcp://contexts/{project_id}/{context_key}`
- `openmcp://models`
- `openmcp://routing-profiles`
- `openmcp://projects/{project_id}/routing-profiles`
- `openmcp://workflows/{project_id}`

## Job states

- `queued` and `running`: wait or cancel.
- `succeeded`: inspect results, then integrate eligible writes.
- `failed`: diagnose, then retry a recoverable stage.
- `cancelled`: terminal until explicitly retried.
- `interrupted`: retry after confirming resumption remains valid.
- `integrated`: repository already contains the write result.
- `integration_conflict`: repository or overlay state changed.

## Parent chains

Set `parent_job_id` for dependent jobs. Children start from their parent's result
commit while preserving the original integration base.

Recommended chain:

```text
forge-write -> sentinel-read -> forge-write fix
```

Integrate the final write job. Integrate the original write when review passes
without a fix.

## Local overlays

Store local rules in ignored `.openmcp.local.toml`:

```toml
[[overlays]]
include = ["config/*.development.json", "themes/**/*.local.css"]
exclude = ["config/private.development.json"]
workflows = ["project-development-write"]
```

Matched files must be Git-ignored. Paths cannot contain symlinks. Includes and
excludes use relative glob patterns. Negated patterns are unsupported.
