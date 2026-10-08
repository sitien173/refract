# MCPServer v2 Migration and Job Subscriptions

## Purpose

Migrate OpenMCP from FastMCP v1 to MCP Python SDK v2 `MCPServer`.
Retain the durable Streamable HTTP daemon. Add job resource notifications so
subscription-aware clients avoid repeated `job_wait` calls.

## Decisions

- Require MCP Python SDK v2 only.
- Keep Streamable HTTP at `/mcp`.
- Keep Starlette and Uvicorn.
- Keep loopback defaults.
- Keep one shared Runtime and scheduler.
- Use a Starlette host around the MCP application.
- Let the SDK lifespan own Runtime creation and closure.
- Access Runtime through injected `Context` only.
- Remove `_ACTIVE_RUNTIME` and `mcp.settings` usage.
- Use `json_response=False` for progress-capable responses.
- Keep every existing tool and resource URI.
- Keep `job_wait` as a compatibility fallback.
- Add `resource_uri` to `SubmissionResult`.
- Use SDK v2 `subscriptions/listen` for job updates.
- Do not add stdio or another job URI scheme.

## Architecture

The module-level `MCPServer` registers tools and resources. Uvicorn serves a
Starlette host. The host mounts the SDK Streamable HTTP application at `/mcp`.

```text
Uvicorn
  -> Starlette host
    -> /mcp
      -> MCPServer Streamable HTTP application
```

The Starlette lifespan starts the SDK session manager. The SDK lifespan loads
launch configuration, configures logging, creates one Runtime, starts recovery
and scheduling, then yields the Runtime. Shutdown drains MCP sessions before
closing Runtime exactly once.

Tools and resources obtain Runtime from:

```python
ctx.request_context.lifespan_context
```

Resources currently using `_active_runtime()` receive an injected `Context`.

## Transport

`MCPServer` receives protocol configuration only. Transport configuration moves
to `streamable_http_app()`.

- `streamable_http_path` remains `/mcp`.
- `json_response` is false.
- HTTP remains stateful.
- The configured host controls transport security checks.
- Uvicorn receives the resolved host and port.
- Multiple Uvicorn workers remain unsupported.

CLI configuration values default to `127.0.0.1:8765`. Explicit command-line
values override them. Host and port remain local launch values. The CLI never
mutates server settings.

## Request Flow

```text
Client request
  -> Streamable HTTP validation
  -> MCPServer handler
  -> injected Context
  -> shared Runtime
  -> SQLite and scheduler
  -> structured MCP result
```

Tools retain explicit structured output. Existing Pydantic result models remain
the public payloads. SDK v2 schema and compatibility text behavior is accepted.
Resources continue returning formatted JSON text with `application/json` MIME
types.

## Job Update Subscriptions

`job_submit` returns the existing job fields plus an exact resource URI:

```json
{
  "job_id": "123",
  "state": "queued",
  "resource_uri": "openmcp://jobs/123"
}
```

Subscription-aware clients follow this sequence:

1. Submit the job.
2. Start `subscriptions/listen` for the exact resource URI.
3. Read the resource immediately.
4. Read it again after each `ResourceUpdated` notification.

The immediate read closes the missed-notification window. Notifications are
not replayed. Reconnected clients start another listener and immediately read
the durable resource.

Runtime and JobRunner share an asynchronous job-update notifier. They publish
after persisted transitions to `queued`, `running`, `succeeded`, `failed`,
`cancelled`, or `interrupted`. A retry publishes the transition back to
`queued`.

Notifications contain only the changed URI. Clients read the current JobView.
Notification delivery failures are logged and never alter job state.

`job_wait` remains available for clients without SDK v2 listener support.

## Error Handling

- SQLite remains the authoritative job state.
- Handler validation continues raising existing value errors.
- MCPServer converts handler failures into protocol errors.
- Unknown job resources keep existing error behavior.
- Notification failures never fail jobs.
- Subscription loss requires reconnect and immediate read.
- Startup failure closes partially created Runtime state.
- Shutdown failure still clears launch configuration.

## Migration

- Change the dependency constraint to `mcp>=2,<3`.
- Regenerate `uv.lock` only through `uv lock`.
- Replace FastMCP imports and construction.
- Move transport settings into the application factory.
- Replace CLI `mcp.settings` access with local values.
- Replace private session-manager test hooks.
- Update SDK protocol attributes to snake_case.
- Add `resource_uri` to `SubmissionResult`.
- Add job transition notifications.

No database migration is required. Stored projects, jobs, events, execution
plans, and contexts remain valid.

## Non-goals

- MCP Python SDK v1 compatibility.
- Stdio transport.
- Legacy standalone SSE transport.
- Multiple Uvicorn workers.
- Notification replay or persistence.
- Removing `job_wait`.
- Changing job scheduling or execution semantics.
- Adding another job resource scheme.

## Testing

- Assert the server uses MCPServer.
- Verify one application creates one shared Runtime.
- Verify Runtime closes exactly once.
- Verify startup and shutdown failure cleanup.
- Verify CLI host and port precedence.
- Verify only `/mcp` exposes MCP.
- Call every tool through an SDK v2 client.
- Read every resource through that client.
- Validate structured tool results.
- Verify `job_submit` returns `resource_uri`.
- Verify each persisted job transition publishes its exact URI.
- Verify subscribed clients read the final JobView.
- Verify immediate reads recover missed notifications.
- Verify notification failures do not fail jobs.
- Verify `job_wait` still reports progress.
- Run all offline tests, package build, doctor, and diff checks.

## Verification

```bash
uv lock
uv sync --all-extras
uv run pytest
uv build
uv run openmcp doctor
git diff --check
```
