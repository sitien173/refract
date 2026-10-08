## Original User Request
Complete the OpenMCP admin configuration dashboard. Implement Phase 2 safe dashboard APIs without exposing file-managed mutations or sensitive execution details.

## Phase
Expose safe dashboard APIs.

## Tasks
- task-1: Add structured dashboard response and error models.
- task-2: Add read endpoints with backend profile resolution and source attribution.
- task-3: Redact sensitive job execution-plan fields.
- task-4: Add loopback and same-origin CSRF-protected context mutation endpoints with expected-value conflicts.

## Context
Phase 1 added global configuration health, revision identity, and per-job revision persistence. The existing Starlette application mounts MCP at `/`. Dashboard routes must live under `/dashboard/api` without shadowing `/mcp`. Backend responses must resolve profile inheritance and value sources. Read responses omit credentials, system prompts, and unrestricted backend arguments. Context instructions are the only mutable dashboard configuration.

## Files
- `src/openmcp/dashboard.py`
- `src/openmcp/models.py`
- `src/openmcp/runtime.py`
- `src/openmcp/server.py`
- `tests/test_dashboard.py`
- `tests/test_runtime.py`
- `tests/test_smoke.py`

## Done When
- Dashboard routes live under `/dashboard/api`.
- Overview separates daemon and configuration health.
- Project responses show declared, inherited, effective, and source values.
- Target responses show health without provider credentials.
- Job responses show revisions and safe plan details.
- System prompts and unrestricted backend arguments remain omitted.
- Context mutations reject non-loopback requests.
- Context mutations require a valid `X-OpenMCP-CSRF` header.
- Context mutations reject stale expected values with HTTP 409.
- CSRF tokens use cryptographically secure randomness.
- Origin checks ignore forwarded headers.
- Errors use stable JSON structures.
- No new MCP mutation tool exists.
- `uv run pytest tests/test_dashboard.py tests/test_runtime.py tests/test_smoke.py`
- `uv run pytest`
- `tgrep -n "dashboard/api|X-OpenMCP-CSRF" src/openmcp tests -g '*.py'`
- `git diff --check`

## Consultation Findings
- Register concrete dashboard routes before the final `Mount("/", app=mcp_application)`. Never add a root catch-all.
- Publish the active `Runtime` through application state owned by OpenMCP. Fail closed with 503 before startup, after shutdown, and after startup failure.
- Dashboard routes require their own Host and Origin protection because MCP transport middleware does not cover outer routes.
- Validate loopback from `request.client.host` using `ipaddress`. Ignore all forwarded headers. Require a loopback Host value for mutations and bootstrap.
- Generate `secrets.token_urlsafe(32)` during each lifespan. Bootstrap it through a loopback-protected, no-store response. Add no CORS headers.
- Mutations require a present, matching Origin and use `secrets.compare_digest` for `X-OpenMCP-CSRF`. Return one generic forbidden envelope.
- Compare and replace context instructions atomically without any suspension point. Treat absent and empty as equivalent. Return HTTP 409 with the current value.
- Preserve both global and project-merged catalogs for source attribution. Handle project self-extension against the global snapshot explicitly.
- Dashboard reads use cached runtime state and must not trigger global reloads. Project failures stay separate from global health.
- Redact execution plans through an explicit allow-list model. Omit prompts, argument values, backend profiles, reasoning settings, and future unknown fields.
- Every database-using endpoint must be `async def` because SQLite connections are thread-bound.
- Use one stable error envelope. Sanitize configuration-originated messages.
- Use the existing raw-ASGI testing pattern rather than adding `httpx`.

## Additional Allowed Files
- `src/openmcp/database.py`
- `tests/test_database.py`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Do not add configuration-file writes or MCP
mutation tools. Keep all read responses minimally necessary and redacted.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
