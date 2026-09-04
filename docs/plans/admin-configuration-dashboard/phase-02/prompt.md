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

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Do not add configuration-file writes or MCP
mutation tools. Keep all read responses minimally necessary and redacted.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
