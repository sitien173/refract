## Original User Request

Execute the `mcpserver-v2-subscriptions` plan. This phase migrates the daemon
from FastMCP v1 to MCP Python SDK v2 `MCPServer`.

## Phase

Serve the current OpenMCP contract through SDK v2.

## Tasks

- task-1: Add failing SDK v2 schema, lifecycle, and CLI tests.
- task-2: Upgrade dependencies and replace FastMCP construction.
- task-3: Rebuild Starlette hosting and Runtime lifespan ownership.
- task-4: Replace private v1 test seams with public v2 behavior.

## Context

Keep Streamable HTTP only at `/mcp`, Starlette and Uvicorn hosting, loopback
defaults, stateful HTTP, and `json_response=False`. Move transport settings to
`streamable_http_app()`. Resolve CLI host and port locally. Remove
`_ACTIVE_RUNTIME` and `mcp.settings` access. Runtime is available only through
the injected `Context`. Preserve tools, resources, scheduler behavior,
persistence, and public errors. Do not add subscriptions in this phase.

## Consultation Findings

MCP SDK v2 rejects `Context` parameters on static resources. The static
runtime-backed `openmcp://projects`, `openmcp://targets`, and
`openmcp://profiles` resources therefore conflict with the plan's Context-only
access rule. The user selected URI templates. Convert only those three static
resources to templates with optional defaulted parameters, preserving exact
URI reads and `application/json` MIME types. Update tests for their template
listing semantics. Do not introduce a replacement runtime global.

## Files

- `pyproject.toml`
- `uv.lock`
- `src/openmcp/server.py`
- `src/openmcp/cli.py`
- `tests/test_server.py`

## Done When

- The phase acceptance criteria in `PLAN.md` all hold.
- `uv lock --check`
- `uv run pytest tests/test_server.py -q`
- `uv run pytest tests/test_execution.py tests/test_scheduler.py tests/test_database.py -q`
- `uv run python -c "from mcp.server import MCPServer; from openmcp.server import mcp; assert isinstance(mcp, MCPServer)"`
- `! tgrep -n -e 'FastMCP' -e 'mcp.settings' -e '_ACTIVE_RUNTIME' src tests`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
