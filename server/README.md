# OpenMCP

OpenMCP is a local coding-agent orchestration daemon.

## Capabilities

- Durable project jobs
- Named context streams
- Health-aware target selection and failover
- Configurable profiles
- Direct directory execution
- Per-project FIFO scheduling

## Architecture

- `server.py` exposes MCP tools, resources, and daemon lifecycle.
- `runtime.py` composes persistence, scheduler, and execution.
- `scheduler.py` serializes each project's jobs.
- `execution.py` runs job lifecycles and target failover.
- `database.py` persists jobs, events, contexts, and target health.

## Installation

OpenMCP supports Windows, macOS, and Linux with Python 3.12 or newer. At
least one configured backend CLI must be on `PATH`.

```bash
uv sync --all-extras
```

Create `~/.openmcp/config.toml` using the explicit configuration shown below.
Then verify and start the daemon:

```bash
uv run openmcp doctor
uv run openmcp serve
```

The default endpoint is `http://127.0.0.1:8765/mcp`.

## Direct project execution

OpenMCP runs jobs directly in each registered directory. Jobs for one project
run in submission order. Jobs for different projects may run concurrently up to
`max_jobs`. OpenMCP does not inspect or mutate project files.

- `implement`, `review`, `consult`, and `other` each run once.
- Failed, cancelled, and interrupted jobs retain their project changes.

## MCP contract

Tools:

- `status()` returns scheduler status.
- `project_register(path, alias)` registers an existing directory.
- `task_guide(task, project_id)` loads workflow and profile guidance.
- `job_submit(project_id, workflow, prompt, context_key, profile)` queues work.
- `job_wait(job_id, timeout_s)` waits for completion or timeout.
  Public waits are bounded to 30 seconds. Omitted and zero values use 30
  seconds; smaller positive values are preserved; larger values are clamped.
  Negative values are rejected. Poll again to observe later job states.
  Terminal jobs return immediately with their structured result.
- `job_cancel(job_id)` cancels queued or running work.
- `job_retry(job_id)` retries failed, cancelled, or interrupted work.

Built-in workflows are `implement`, `review`, `consult`, and `other`.
Project-local custom workflow files are not loaded.

Example submission:

```json
{
  "project_id": "project-uuid",
  "workflow": "implement",
  "prompt": "Add validation for empty names and run focused tests.",
  "context_key": "validation/implement",
  "profile": "quality"
}
```

Job states are `queued`, `running`, `succeeded`, `failed`, `cancelled`, and
`interrupted`. A completed job exposes `result.text` and `result.error`.

### Subscription-aware job updates

`job_submit` and `job_retry` return `resource_uri`, using the exact
`openmcp://jobs/{job_id}` URI for the durable job resource. Clients that support
SDK v2 `subscriptions/listen` can observe transitions without polling:

1. Submit the job and retain its `resource_uri`.
2. Open `subscriptions/listen` with that URI in `resource_subscriptions`.
3. After the listen acknowledgement, immediately read the job resource. This
   closes the race with queued or terminal transitions that happened before the
   listener was active.
4. When `notifications/resources/updated` arrives for the URI, read the same
   resource again; the notification carries no duplicated job payload.

If a listener disconnects or misses an update, reconnect, establish the exact
URI subscription again, and perform another immediate read. SQLite remains the
source of truth. Clients without subscriptions can continue using
`job_wait`, whose public wait remains bounded to 30 seconds.

## Configuration

OpenMCP reads `~/.openmcp/config.toml`.

Configuration is explicit. The file must define non-empty `targets` and
`profiles` sections, plus `[daemon].default_profile` naming a defined profile.
OpenMCP does not fabricate targets, profiles, or a default profile.

```toml
[daemon]
host = "127.0.0.1"
port = 8765
max_jobs = 4
history_turns = 8
history_bytes = 65536
default_profile = "balanced"

[[targets]]
id = "forge-primary"
backend = "codex"

[[targets]]
id = "sage-primary"
backend = "pi"
model = "gpt-5.6-sol"
isolated = true
read_only = true

[[targets]]
id = "sentinel-primary"
backend = "pi"
model = "gpt-5.6-sol"
isolated = true
read_only = true

[profiles.balanced]
implement = "forge-primary"
review = "sentinel-primary"
consult = "sage-primary"
other = "forge-primary"
```

A profile may explicitly inherit one parent. Child workflow selections replace
the parent's selection for that workflow. Profiles may be partial; an unmapped
workflow is rejected when its execution plan is resolved.

```toml
[profiles.fast]
extends = "balanced"
implement = ["forge-primary"]

[profiles.advisor]
consult = "sage-primary"
```

A workflow selects intent. A profile maps each workflow to one target or an
ordered target list. Targets hold backend execution policy.

Targets, profiles, and project configuration reload for later submissions.
Submitted jobs retain immutable selection snapshots.

## Pi isolation

Isolated Pi targets disable context files, extensions, skills, prompt templates,
and project approvals. Read-only Pi targets receive only `read`, `grep`, `find`,
and `ls`. Normal Pi targets receive `--approve` after configurable args.

## Upgrade from previous schemas

The first startup rebuilds legacy job records. Completed history remains
readable. Legacy queued and running jobs become interrupted. Historical
repository metadata is discarded during migration.

## Direct Python compatibility API

Existing Python callers can invoke one backend directly:

```python
from openmcp.server import run

result = await run("codex", "Summarize the repository.", "/absolute/project")
```

New integrations should use durable MCP jobs. Direct calls do not load target
configuration and return `success`, `SESSION_ID`, `agent_messages`, and `error`.

## Development

```bash
uv run pytest
uv run pytest -m live
uv build
```
