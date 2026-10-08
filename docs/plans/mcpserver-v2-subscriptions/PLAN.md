# MCPServer v2 Migration and Job Subscriptions Plan

Status: ACTIVE
Context key: `mcpserver-v2-subscriptions`

## Confirmed Outcome

Replace FastMCP v1 with MCP Python SDK v2 `MCPServer`. Keep the durable
Streamable HTTP daemon at `/mcp`. Preserve one shared Runtime. Add SDK v2 job
resource notifications while retaining `job_wait` as fallback.

## Scope

- Migrate server construction, lifespan, transport, CLI, and tests.
- Require MCP Python SDK v2 only.
- Use `json_response=False`.
- Remove `_ACTIVE_RUNTIME` and `mcp.settings` usage.
- Add `resource_uri` to job submission results.
- Publish exact job resource updates after persisted transitions.
- Document subscription-aware client behavior.
- Preserve scheduling, execution, persistence, and resource URIs.

## Risks

- Incorrect lifespan ownership can create multiple schedulers.
- Private SDK seams can make lifecycle tests brittle.
- Transport security can reject valid loopback requests.
- Notification failures must never affect durable jobs.
- Missed notifications require an immediate resource read.
- SDK schema changes can alter structured tool results.

# ROUTE

- Sequence: consult complete -> implement -> review
- Implement Profile: Resolve at execution
- Consult Profile: Resolve at execution
- Review Profile: Resolve at execution
- Reason: Migration crosses transport, lifecycle, and scheduler boundaries.
- Done When: Fresh tests, build, doctor, and diff checks pass.

### Phase 1: Run the daemon on MCPServer v2

**Task Guide Input:** Migrate OpenMCP from MCP Python SDK v1 FastMCP to SDK v2
MCPServer. Keep Streamable HTTP only at `/mcp`, Starlette and Uvicorn hosting,
loopback defaults, stateful HTTP, `json_response=False`, and one shared daemon
Runtime. Move transport settings into `streamable_http_app()`. Replace CLI
server-setting mutation with local host and port resolution. Remove
`_ACTIVE_RUNTIME`. Access Runtime only through injected Context. Preserve all
current tools, resources, scheduler behavior, persistence, and public errors.
Update the dependency lock and v2-facing tests. Do not add job subscriptions in
this phase.

**Goal:** Serve the existing OpenMCP contract through SDK v2.

**Files:**

- Modify: `pyproject.toml`
- Modify through `uv lock`: `uv.lock`
- Modify: `src/openmcp/server.py`
- Modify: `src/openmcp/cli.py`
- Modify: `tests/test_server.py`

**Tasks:**

1. Add failing SDK v2 schema, lifecycle, and CLI tests.
2. Upgrade dependencies and replace FastMCP construction.
3. Rebuild Starlette hosting and Runtime lifespan ownership.
4. Replace private v1 test seams with public v2 behavior.

**Acceptance Criteria:**

- The dependency resolves MCP SDK version two only.
- Direct Starlette and Uvicorn imports have direct dependencies.
- No FastMCP import remains.
- No `mcp.settings` access remains.
- No `_ACTIVE_RUNTIME` global remains.
- MCP remains available only at `/mcp`.
- Streamable HTTP is stateful and allows progress responses.
- One application lifespan creates one Runtime.
- Every request receives that Runtime through Context.
- Shutdown closes Runtime exactly once.
- Startup and shutdown failures clear launch configuration.
- CLI flags override configured host and port.
- Transport security receives the resolved host.
- All existing tools retain names and structured outputs.
- All existing resources retain URIs and MIME types.
- SDK protocol model assertions use v2 attributes.
- Scheduler and persistence tests remain unchanged and passing.

**Reviewer Checklist:**

- Confirm no Runtime exists per MCP session.
- Confirm SDK session management runs exactly once.
- Confirm MCP sessions drain before Runtime closure.
- Confirm no private SDK attributes support production logic.
- Confirm port is passed only to Uvicorn.
- Confirm loopback host validation remains secure.
- Confirm multiple Uvicorn workers are not introduced.
- Confirm no job subscription behavior entered this phase.

**Verification Checks:**

- `uv lock --check`
- `uv run pytest tests/test_server.py -q`
- `uv run pytest tests/test_execution.py tests/test_scheduler.py tests/test_database.py -q`
- `uv run python -c "from mcp.server import MCPServer; from openmcp.server import mcp; assert isinstance(mcp, MCPServer)"`
- `! tgrep -n -e 'FastMCP' -e 'mcp.settings' -e '_ACTIVE_RUNTIME' src tests`
- `git diff --check`

**Commit:** `refactor(server): migrate to mcpserver v2`

### Phase 2: Publish durable job resource updates

**Task Guide Input:** Add subscription-driven job updates to the SDK v2 OpenMCP
server. Extend SubmissionResult with the exact existing
`openmcp://jobs/{job_id}` resource URI. Publish SDK v2 ResourceUpdated events
after persisted queued, running, succeeded, failed, cancelled, interrupted, and
retry transitions. Use `subscriptions/listen`. Keep `job_wait` unchanged as a
fallback. Notification failures must be logged and must never alter jobs.
Document the submit, listen, immediate-read, and notification-read client flow.
Do not add notification persistence, replay, stdio, another URI scheme, or
scheduler changes.

**Goal:** Let capable clients observe jobs without polling.

**Files:**

- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/execution.py`
- Modify: `src/openmcp/server.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`

**Tasks:**

1. Add failing submission URI and transition notification tests.
2. Add one asynchronous notifier across Runtime and JobRunner.
3. Connect notifications to the MCPServer subscription bus.
4. Document listener ordering, recovery, and fallback behavior.

**Acceptance Criteria:**

- Every SubmissionResult includes `resource_uri`.
- Submit and retry return the existing job resource URI.
- Each persisted state transition publishes that exact URI.
- Notifications occur only after durable state changes.
- Notifications contain no duplicated job payload.
- Notification failures are logged and suppressed.
- Notification failures never change job outcomes.
- Listener clients can read the final JobView.
- Immediate reads recover transitions missed before listening.
- Reconnected clients recover through another immediate read.
- URI subscription matching remains exact.
- `job_wait` retains its 30-second bounded behavior.
- Existing job resource reads remain unchanged.
- No database migration is introduced.
- README describes SDK v2 `subscriptions/listen`.

**Reviewer Checklist:**

- Confirm SQLite remains authoritative.
- Confirm notification code cannot fail job execution.
- Confirm all terminal and retry transitions notify.
- Confirm queued cancellation notifies once persisted.
- Confirm notification tasks cannot leak during shutdown.
- Confirm no internal polling was introduced.
- Confirm no second job URI scheme exists.
- Confirm legacy `job_wait` clients remain supported.

**Verification Checks:**

- `uv run pytest tests/test_server.py tests/test_execution.py -q`
- `uv run pytest -q`
- `uv build`
- `uv run openmcp doctor`
- `tgrep -n -e 'resource_uri' -e 'subscriptions/listen' src tests README.md`
- `git diff --check`

**Commit:** `feat(server): publish job resource updates`

## Final Review

Specification review must confirm both phase outcomes. Quality review must
inspect only each phase delta. Fresh final evidence requires:

```bash
uv lock --check
uv run pytest -q
uv build
uv run openmcp doctor
git diff --check
```

