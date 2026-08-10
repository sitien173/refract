# Project Overview

OpenMCP is a loopback HTTP orchestration daemon. It exposes durable project jobs
through MCP. Jobs use built-in workflows, profiles, named contexts, direct
repository execution, and explicit job results.

## Repository Structure

```text
src/openmcp/
  backends/           provider-specific CLI adapters and classification
  backend_runner.py   direct Python invocation compatibility service
  cli.py              serve and doctor commands
  config.py           targets, profiles, and CLI args
  database.py         SQLite state and migrations
  drivers.py          internal provider dispatch
  execution.py        job lifecycle and target execution
  models.py           public structured results
  planning.py         immutable execution-plan snapshots
  processes.py        cross-platform process-group lifecycle
  repositories.py     direct Git operations
  runtime.py          public orchestration facade
  scheduler.py        per-project FIFO scheduler
  server.py           MCP tools, resources, and daemon lifecycle
  workflows.py        fixed workflow validation
```

## Development Commands

```bash
uv sync --all-extras
uv run pytest
uv run pytest -m live
uv run openmcp doctor
uv run openmcp serve
uv build
```

## Public Contract

Tools: `status`, `project_register`, `task_guide`,
`job_submit`, `job_wait`, `job_cancel`, and `job_retry`.

Jobs execute directly in registered repositories. The scheduler serializes all
jobs per project while allowing cross-project concurrency. Successful
`implement` jobs commit immediately. `review` and `consult` never commit.

The public job tools are `job_submit`, `job_wait`, `job_cancel`, and
`job_retry`. Jobs have one result and no stages, parent links, private branches,
overlays, artifacts, or integration step.

## Target execution policy

Targets own provider execution settings: `model`, `backend_profile`,
`reasoning`, `system_prompt`, `isolated`, `read_only`, and backend-specific
argv `args`. Drivers compile those fields into transport-only backend calls.
Target args are individual argv tokens, never shell syntax. Target policy and
args are captured in the immutable execution plan for each job.

## Pi Isolation

Targets can set `isolated`, `read_only`, and `system_prompt`. Isolated Pi
invocations disable context files, extensions, skills, prompt templates, and
project approvals. Read-only targets receive only `read`, `grep`, `find`, and
`ls` tools. Normal Pi targets receive `--approve` after configurable args.

## Code Conventions

- Use `from __future__ import annotations`.
- Use `@dataclass(slots=True)` for parameter types.
- Define `__all__` in package modules.
- Use `get_logger()`. Never print from library code.
- Keep provider names inside drivers and configuration.
- Preserve structured MCP result models.

## Testing

Offline tests cover command construction, scheduler behavior, persistence,
direct commits, cancellation, migration, and recovery. Live tests require
provider CLIs. Normal test runs skip live markers.

## Security Guardrails

- Never store credentials in this repository.
- Never log API keys or environment secrets.
- Review every subprocess command change.
- Review classifier and scheduler retry changes.
- Never modify Antigravity settings to select a model; pass `agy --model` per invocation.
- Do not persist or mutate provider settings outside target configuration and
  the driver compilation boundary.
- Update `uv.lock` only through `uv lock`.
- Keep Sentinel and Sage read-only by default.
- Keep HTTP bound to loopback by default.
- Git isolation is not a security sandbox. Permission-bypassing write agents can access the host and parent repository.

## Adding targets and profiles

Targets configure providers, models, policies, and backend argv options.
Profiles map built-in workflows directly onto targets. Configuration and project
selection reload for new submissions, while submitted jobs retain their
immutable plan. OpenMCP does not load project-defined workflows.
