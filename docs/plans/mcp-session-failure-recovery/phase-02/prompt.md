## Original User Request

Fix OpenMCP after backend errors, retries, or timeouts. Keep API
and MCP tool calls responsive after those outcomes.

## Phase

Own one runtime per daemon.

## Tasks

- task-1: Add singleton and shutdown lifecycle tests.
- task-2: Add application-scoped runtime ownership.
- task-3: Route CLI serving through the application.
- task-4: Constrain MCP SDK compatibility below version two.

## Context

FastMCP v1 enters its configured server lifespan per MCP session.
The current lifespan creates and closes `Runtime`. Every session can
therefore start another scheduler, interrupt active database jobs,
clear `_ACTIVE_RUNTIME`, and close its own database.

Current MCP documentation requires a top-level ASGI lifespan to run
the session manager when mounting the streamable HTTP application.
The runtime must live in that same application lifespan. Session
lifespan should only yield the already-active runtime.

The CLI currently calls `mcp.run(transport="streamable-http")`.
Preserve host and port overrides while routing through the new
application factory. Do not migrate to MCP SDK v2.

## Files

- `src/openmcp/server.py`
- `src/openmcp/cli.py`
- `tests/test_server.py`
- `tests/test_dashboard.py`
- `pyproject.toml`
- `uv.lock`
- `docs/plans/mcp-session-failure-recovery/phase-02/notes.md`
- `docs/plans/mcp-session-failure-recovery/phase-02/journal.md`

## Done When

- Daemon startup creates exactly one runtime.
- Every MCP session receives that same runtime.
- Ending one session does not close the runtime.
- Starting another session does not interrupt jobs.
- Dashboard endpoints work before any MCP session.
- Dashboard remains available after session closure.
- Global resources remain available between sessions.
- Daemon shutdown closes the runtime exactly once.
- Cleanup clears globals after close failures.
- Existing host and port overrides still work.
- Retryable and failed jobs do not poison later calls.
- MCP SDK remains constrained below version two.
- `uv run pytest tests/test_server.py tests/test_dashboard.py -q`
- `uv run pytest tests/test_execution.py::test_failed_execution_leaves_changes_and_preserves_dirty_preflight tests/test_execution.py::test_retries_reuse_targets_after_each_failover_pass tests/test_execution.py::test_cancellation_interrupts_retry_backoff -q`
- `uv lock --check`
- `uv run pytest -q`
- `uv build`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this
phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
