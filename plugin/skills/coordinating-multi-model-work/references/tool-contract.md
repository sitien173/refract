# OpenMCP Tool Contract

Default endpoint: `http://127.0.0.1:8765/mcp`.

## Tools

| Tool | Required | Optional | Purpose |
| --- | --- | --- | --- |
| `status` | — | — | Return scheduler health and queue counts. |
| `reload` | — | — | Reload targets and profiles for later submissions. |
| `doctor` | `path` | — | Return read-only client checks. |
| `project_register` | `path` | `alias` | Register a clean attached Git root. |
| `task_guide` | `task` | `project_id` | Return workflow/profile guidance. |
| `job_submit` | `project_id`, `workflow`, `prompt` | `commit_message`, `context_key`, `profile` | Queue one job. |
| `job_wait` | `job_id` | `timeout_s` | Wait for completion or timeout. |
| `job_cancel` | `job_id` | — | Cancel queued or running work. |
| `job_retry` | `job_id` | — | Retry a failed, cancelled, or interrupted whole job. |

Tool names may be client-namespaced; match their OpenMCP suffixes.

## Workflows

| Workflow | Behavior |
| --- | --- |
| `implement` | Commit successful tracked and non-ignored untracked changes directly. |
| `review` | Return review text and leave the repository unchanged. |
| `consult` | Return advice and leave the repository unchanged. |

Only these workflows are valid. `commit_message` is valid only for `implement`.
Guidance names workflows and optional profiles, never targets or providers.

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

## Execution Semantics

- Jobs run in the registered root on the attached branch current at start.
- Preflight requires a clean repository.
- Same-project jobs execute FIFO without overlap; different projects may run
  concurrently up to `max_jobs`.
- Successful `implement` returns its commit; no-change success returns existing
  HEAD.
- Successful `review` and `consult` preserve clean HEAD.
- Started unsuccessful jobs reset to `base_commit` and remove non-ignored
  untracked files.
- Dirty-preflight failures preserve existing changes.
- Ignored files are visible and are never committed or restored.

## Jobs

States: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `interrupted`.

A job includes `base_commit`, `result.text`, `result.commit`, and `result.error`.
A queued job has no base until execution begins.

`job_retry` reuses the ID and immutable plan, retries the whole job, and selects
a new base at execution. Use a new submission when the prompt must change.

`reload` does not alter submitted plans. Report `restart_required`; static daemon
and logging changes require restart.
