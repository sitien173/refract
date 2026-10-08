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

Consultation requires this lifecycle order:

1. Build `mcp.streamable_http_app()` once.
2. Create and start one runtime.
3. Set `_ACTIVE_RUNTIME`.
4. Enter `mcp.session_manager.run()` once.
5. Serve all mounted routes.
6. Exit the session manager.
7. Clear `_ACTIVE_RUNTIME`.
8. Close the runtime exactly once.
9. Clear `_DAEMON_CONFIG`, including close failures.

Use an outer `Starlette` application. Mount the MCP application at
`/`. Session lifespan must only yield `_active_runtime()`. It must
never create, start, or close runtime state.

Build the application after CLI overrides. Pass the selected host
and port directly to Uvicorn. Do not mutate router lifespan
internals. Do not enter the child application lifespan. Do not run
the session manager twice.

Tests must enter application lifespan explicitly. HTTPX ASGI
transport does not enter it automatically. Assert shutdown ordering,
sequential session identity, dashboard availability before sessions,
global resource availability, and CLI precedence.

Constrain the dependency exactly as `mcp[cli]>=1.21.2,<2`. Update
only through `uv lock`, then inspect the lock diff.

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
