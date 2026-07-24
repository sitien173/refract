# OpenMCP Tool Contract

Default endpoint: `http://127.0.0.1:8765/mcp`.

## Tools

| Tool | Required | Optional | Purpose |
| --- | --- | --- | --- |
| `status` | — | — | Return scheduler health and queue counts. |
| `reload` | — | — | Reload targets and profiles for later submissions. |
| `doctor` | `path` | — | Return read-only client checks. |
| `project_register` | `path` | `alias` | Register your project directory. |
| `task_guide` | `task` | `project_id` | Return workflow/profile guidance. |
| `job_submit` | `project_id`, `workflow`, `prompt` | `context_key`, `profile` | Queue one job. |
| `job_wait` | `job_id` | `timeout_s` | Wait for completion or timeout. |
| `job_cancel` | `job_id` | — | Cancel queued or running work. |
| `job_retry` | `job_id` | — | Retry a failed, cancelled, or interrupted whole job. |

Tool names may be client-namespaced; match their OpenMCP suffixes.

## Workflows

| Workflow | Behavior |
| --- | --- |
| `implement` | Run the prompt in the project directory and leave every filesystem change in place; you commit. |
| `review` | Return review text; run against a read-only target so it cannot mutate files. |
| `consult` | Return advice; run against a read-only target so it cannot mutate files. |

Only these workflows are valid. No workflow commits, resets, or restores; you
own all Git. Guidance names workflows and optional profiles, never targets or
providers.

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

- Jobs run in the registered directory on the branch current at start.
- OpenMCP never checks cleanliness; a dirty working tree does not block
  submission.
- Same-project jobs execute FIFO without overlap; different projects may run
  concurrently up to `max_jobs`. This FIFO is the only serialization; add no job
  locking of your own.
- OpenMCP never commits, resets, or restores. Filesystem changes from every
  terminal state (success, failure, cancellation, interruption) remain on disk
  for you to inspect and reconcile.
- Prevent mutation for `review` and `consult` with a read-only target, not a
  workflow flag.
- A worker session is resumed by `project_id` + `context_key` + `workflow` +
  target key, keyed primarily on `context_key`. Reusing one `context_key` across
  jobs continues the same session per workflow.

## Jobs

States: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `interrupted`.

A job exposes `result.text` on success and `result.error` on failure. OpenMCP
stores no commit or base fields; read Git state directly from the working tree.

`job_retry` reuses the ID and immutable plan and reruns the whole job. It does
not reset the working tree, and a daemon restart does not restore files;
reconcile existing changes before retrying. Use a new submission when the prompt
must change.

`reload` does not alter submitted plans. Report `restart_required`; static daemon
and logging changes require restart.
