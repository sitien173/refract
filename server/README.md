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

- `implement`, `review`, and `consult` each run once.
- Failed, cancelled, and interrupted jobs retain their project changes.

## MCP contract

Tools:

- `status()` returns scheduler status.
- `reload()` reloads targets and profiles for later submissions.
- `doctor(path)` returns read-only client integration checks.
- `project_register(path, alias)` registers an existing directory.
- `task_guide(task, project_id)` loads workflow and profile guidance.
- `job_submit(project_id, workflow, prompt, context_key, profile)` queues work.
- `job_wait(job_id, timeout_s)` waits for completion or timeout.
- `job_cancel(job_id)` cancels queued or running work.
- `job_retry(job_id)` retries failed, cancelled, or interrupted work.

Built-in workflows are `implement`, `review`, and `consult`. Project-local
custom workflow files are not loaded.

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
`interrupted`. A completed job exposes `result.text`, `result.commit`, and
`result.error`.

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
capabilities = ["code"]

[[targets]]
id = "sage-primary"
backend = "pi"
model = "gpt-5.6-sol"
isolated = true
read_only = true
capabilities = ["consult"]

[[targets]]
id = "sentinel-primary"
backend = "pi"
model = "gpt-5.6-sol"
isolated = true
read_only = true
capabilities = ["review"]

[profiles.balanced]
implement = "forge-primary"
review = "sentinel-primary"
consult = "sage-primary"
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
ordered target list. Targets hold backend execution policy. Every target must
advertise the capability required by its workflow.

Targets, profiles, and project configuration reload for later submissions.
Submitted jobs retain immutable selection snapshots.

## Pi isolation

Isolated Pi targets disable context files, extensions, skills, prompt templates,
and project approvals. Read-only Pi targets receive only `read`, `grep`, `find`,
and `ls`. Normal Pi targets receive `--approve` after configurable args.

## Upgrade from worktree jobs

The first startup rebuilds legacy job records. Completed history remains
readable. Legacy queued and running jobs become interrupted. Historical
unintegrated commits are not applied to the current branch.

OpenMCP does not remove historical worktrees or `openmcp/*` branches. Inspect
registered repositories with `git worktree list` and remove obsolete entries
manually before running `git worktree prune`. Delete `~/.openmcp/worktrees/`
only after confirming no listed worktree is needed.

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
