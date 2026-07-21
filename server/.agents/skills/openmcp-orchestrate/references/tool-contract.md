# OpenMCP tool contract

Default endpoint: `http://127.0.0.1:8765/mcp`.

## Tools

| Tool | Required inputs | Optional inputs | Purpose |
| --- | --- | --- | --- |
| `status` | | | Return scheduler health and queue counts. |
| `reload` | | | Reload global targets and profiles. |
| `doctor` | `path` | | Return read-only integration checks. |
| `project_register` | `path` | `alias` | Register a clean Git root. |
| `task_guide` | `task` | `project_id` | Load workflow/profile guidance. |
| `job_submit` | `project_id`, `workflow`, `inputs` | `context_key`, `parent_job_id`, `profile` | Queue durable work. |
| `job_wait` | `job_id` | `timeout_s`, `include_stage_outputs` | Wait for completion or timeout. |
| `job_cancel` | `job_id` | | Cancel queued or running work. |
| `job_retry` | `job_id` | `from_stage` | Retry failed or interrupted work. |
| `job_integrate` | `job_id` | | Fast-forward a successful write. |

Tool names may be client-namespaced; match OpenMCP suffixes.

`status` returns `status`, `workers`, `active_jobs`, and `queued_jobs`.

`reload` returns `success`, target/profile counts, and `restart_required`.
Running jobs retain immutable plans. Changed `home`, `host`, `port`, `max_jobs`,
`history_turns`, `history_bytes`, or logging settings require restart.

`doctor` never mutates repositories.

## Built-in workflows

| Workflow | Mode | Behavior |
| --- | --- | --- |
| `implement` | Write | Preserves changes for explicit integration. |
| `review` | Read | Reviews an implementation or project. |
| `consult` | Read | Inspects, analyzes, or advises. |

Only these workflows are available. Project `.openmcp/workflows/*.yaml` files
are not loaded. The former `read` and `write` names are unsupported.

`task_guide` returns recommendations containing a `workflow` and optional
`profile`. Pass those values to `job_submit`; omit `profile` to use the default.
Target IDs and provider names are not submission fields.

Common implementation inputs:

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
- `openmcp://targets`
- `openmcp://profiles`
- `openmcp://projects/{project_id}/profiles`
- `openmcp://workflows/{project_id}`

## Job states

- `queued`, `running`: wait or cancel.
- `succeeded`: inspect results and integrate eligible writes.
- `failed`: diagnose, then retry recoverable work.
- `cancelled`: terminal until explicitly retried.
- `interrupted`: retry after confirming resumption is useful.
- `integrated`: repository contains the write result.
- `integration_conflict`: repository or overlay state changed.

## Parent chains

Set `parent_job_id` for dependent jobs. Children start from the parent's result
commit while preserving the original integration base.

```text
implement -> review -> implement fix
```

Integrate the final implementation, or the original implementation when review
passes without a fix.

## Local overlays

```toml
[[overlays]]
include = ["config/*.development.json", "themes/**/*.local.css"]
exclude = ["config/private.development.json"]
workflows = ["implement"]
```

Matched files must be Git-ignored. Paths cannot contain symlinks. Use relative
globs and explicit excludes.
