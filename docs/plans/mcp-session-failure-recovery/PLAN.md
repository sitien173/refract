# MCP Session Failure Recovery Plan

Status: ACTIVE
Context key: `mcp-session-failure-recovery`

## Confirmed Problem

OpenMCP has two coupled failure modes.

First, MCP `job_wait` defaults to unlimited waiting. Codex expires
tool calls after 300 seconds. Later calls queue behind that wait.
Their response receivers disappear before OpenMCP responds.

Second, FastMCP v1 enters server lifespan per session. OpenMCP
therefore creates one `Runtime` per MCP session. Session closure
stops its scheduler and clears dashboard runtime state. Another
session can also interrupt jobs owned by the first runtime.

Backend errors and retries remain job-scoped. They only increase
the time exposed to these transport and lifecycle bugs.

## Design Decisions

- Bound only the public MCP wait operation.
- Keep internal runtime waits unchanged.
- Use a 30-second maximum MCP wait.
- Reject negative MCP wait values.
- Treat explicit zero as the safe maximum.
- Own one runtime through ASGI application lifespan.
- Share that runtime across every MCP session.
- Close it once during daemon shutdown.
- Keep backend timeout and retry policies unchanged.
- Keep MCP SDK v1 during this fix.
- Constrain the dependency below version two.
- Defer the SDK v2 migration separately.
- Do not preserve sessions across daemon restarts.

## Out of Scope

- Backend outcome classification changes.
- Retry count or backoff changes.
- Provider timeout policy changes.
- Client reconnection implementation.
- MCP SDK v2 migration.
- Dashboard feature changes.

# ROUTE

- Sequence: consult -> implement -> review
- Implement Profile: Resolve at execution
- Consult Profile: Resolve at execution
- Review Profile: Resolve at execution
- Reason: Runtime ownership crosses transport and scheduler boundaries.
- Done When: Bounded waits and singleton lifecycle pass fresh checks.

### Phase 1: Bound MCP job waits

**Task Guide Input:** Prevent public MCP `job_wait` calls from
outliving client tool-call budgets. Default waits to 30 seconds.
Clamp longer and explicit-zero waits to 30 seconds. Reject negative
values. Preserve unlimited waiting inside `Runtime` and
`ProjectScheduler`. Return the latest durable job state after timeout.

**Profile:** Resolve at execution

**Goal:** Keep later MCP calls responsive during long jobs.

**Files:**

- Modify: `src/openmcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

**Tasks:**

1. Add failing tests for default and bounded waits.
2. Add minimal MCP-only timeout normalization.
3. Document bounded polling and terminal-state behavior.

**Acceptance Criteria:**

- Omitted `timeout_s` waits at most 30 seconds.
- Explicit zero waits at most 30 seconds.
- Values above 30 seconds are clamped.
- Negative values fail before scheduler waiting.
- Terminal jobs return without waiting.
- Timeout returns the latest durable `JobView`.
- Runtime and scheduler zero semantics remain unchanged.
- `job_cancel` becomes reachable after one bounded wait.

**Reviewer Checklist:**

- Confirm no backend timeout behavior changed.
- Confirm no retry policy behavior changed.
- Confirm polling returns structured job results.
- Confirm validation cannot create infinite waits.

**Verification Checks:**

- `uv run pytest tests/test_server.py -q`
- `uv run pytest tests/test_execution.py::test_retries_reuse_targets_after_each_failover_pass tests/test_execution.py::test_cancellation_interrupts_retry_backoff -q`

**Commit:** `fix(server): bound MCP job waits`

### Phase 2: Own one runtime per daemon

**Task Guide Input:** Replace per-session runtime ownership with one
ASGI application-scoped `Runtime`. Start it once before serving.
Yield the same instance to every MCP session. Keep dashboard and
global resources active between sessions. Close the runtime once
during daemon shutdown. Preserve configured host and port handling.
Constrain the current implementation to MCP SDK v1.

**Profile:** Resolve at execution

**Goal:** Prevent session closure from poisoning daemon state.

**Files:**

- Modify: `src/openmcp/server.py`
- Modify: `src/openmcp/cli.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_dashboard.py`
- Modify: `pyproject.toml`
- Modify through `uv lock`: `uv.lock`

**Tasks:**

1. Add failing singleton and shutdown lifecycle tests.
2. Add an application factory with combined lifespan.
3. Route CLI serving through that application.
4. Constrain MCP SDK compatibility below version two.

**Acceptance Criteria:**

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
- The lockfile matches declared dependency constraints.

**Reviewer Checklist:**

- Confirm the ASGI lifespan owns runtime creation.
- Confirm session lifespan never owns runtime cleanup.
- Confirm session-manager lifespan runs exactly once.
- Confirm shutdown cannot double-close the database.
- Confirm no private scheduler state is shared incorrectly.
- Confirm no new dependency was added unnecessarily.
- Confirm SDK v2 migration remains out of scope.

**Verification Checks:**

- `uv run pytest tests/test_server.py tests/test_dashboard.py -q`
- `uv run pytest tests/test_execution.py::test_failed_execution_leaves_changes_and_preserves_dirty_preflight tests/test_execution.py::test_retries_reuse_targets_after_each_failover_pass tests/test_execution.py::test_cancellation_interrupts_retry_backoff -q`
- `uv lock --check`
- `uv run pytest -q`
- `uv build`

**Commit:** `fix(server): own runtime for daemon lifetime`

## Final Review

Specification review must confirm both root causes are covered.
Quality review must inspect only both implementation commits.

Fresh final evidence requires:

- `uv lock --check`
- `uv run pytest -q`
- `uv build`

The live smoke check must use two sequential MCP sessions. It must
also query dashboard status between and after those sessions.
