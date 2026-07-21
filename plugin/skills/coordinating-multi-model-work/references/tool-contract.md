# OpenMCP Tool Contract

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

Tool names may be client-namespaced; match their OpenMCP suffixes.

`status` returns `status`, `workers`, `active_jobs`, and `queued_jobs`.

`reload` returns `success`, target/profile counts, and `restart_required`.
Running jobs retain immutable plans. Changes to `home`, `host`, `port`,
`max_jobs`, `history_turns`, `history_bytes`, or logging require restart.

`doctor` never mutates repositories.

## Built-in Workflows

| Workflow | Mode | Inputs | Result |
| --- | --- | --- | --- |
| `implement` | Write | required `prompt`, optional `commit_message` | Text and optional commit |
| `review` | Read | required `prompt` | Review text |
| `consult` | Read | required `prompt` | Analysis text |

Only these workflows are available. Project custom workflow files are not
loaded. The former `read` and `write` workflow names are unsupported.

`task_guide` returns recommendations containing `workflow` and optional
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

## Job States

- `queued`, `running`: wait or cancel.
- `succeeded`: inspect results and integrate eligible writes.
- `failed`: diagnose, then retry recoverable work.
- `cancelled`: terminal until explicitly retried.
- `interrupted`: retry only when resumption remains useful.
- `integrated`: repository contains the write result.
- `integration_conflict`: repository or overlay state changed.

## Parent Chains

A child starts from the successful parent's result commit and preserves the
chain's original integration base.

```text
implement -> review
implement -> review; implement fix from the latest implement commit
```

Read-only jobs do not produce commits. They can inspect an implementation as a
child, but cannot anchor a later child. Put their findings in the next prompt
and use the latest successful `implement` job as the Git parent.

Integrate the final implementation, or the original implementation when review
passes without a fix. Never integrate `review` or `consult`.

## Local Overlays

```toml
[[overlays]]
include = ["config/*.development.json", "themes/**/*.local.css"]
exclude = ["config/private.development.json"]
workflows = ["implement"]
```

Matched files must be Git-ignored. Paths cannot contain symlinks. Use relative
globs and explicit excludes; never expose secrets.
