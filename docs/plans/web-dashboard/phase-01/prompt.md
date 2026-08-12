## Original User Request
Build an in-process read-only web dashboard and monitor for the OpenMCP daemon.

## Phase
Phase 1 — Read-only monitor: operator can watch daemon status, jobs, projects, and target health in a browser.

## Tasks
- task-1: In a new `src/openmcp/dashboard.py`, register read-only JSON endpoints via `@mcp.custom_route`: `GET /dashboard/api/status`, `/projects`, `/projects/{id}/jobs`, `/jobs/{id}`, `/jobs/{id}/events`, `/targets`, `/profiles`. Each resolves `_active_runtime()` (custom routes get a raw Starlette `Request`, not an MCP `Context`), returns JSON from existing runtime/database methods, reuses `models.py` and the `_json` helper, maps missing runtime to `503` and unknown ids to `404`.
- task-2: Register static routes: `GET /dashboard` serves `index.html`; `/dashboard/assets/...` serves `dashboard_static/`. Wire route registration from `server.py` setup without disturbing the existing `/mcp` behavior.
- task-3: Build a single-page Alpine.js SPA (Alpine vendored locally under `dashboard_static/vendor/`, no build step): tabbed Overview (status tiles + targets health grid), Jobs (state-filtered table + detail panel with events), Projects list. Poll status/lists ~3s, open job detail ~2s, pause polling on `visibilitychange`.
- task-4: Add `tests/test_dashboard.py` using Starlette `TestClient` against a `Runtime` on a temp DB, reusing existing fixtures.

## Context
- MCP server is `FastMCP` (Starlette + uvicorn) created at `src/openmcp/server.py:46`; run via `server.mcp.run(transport="streamable-http")` in `cli.py`.
- `@mcp.custom_route(path, methods=[...])` registers arbitrary Starlette routes on the same uvicorn/port; documented for admin APIs and bypasses auth. Register these before `run()`.
- Live daemon state: module global `_active_runtime()` at `server.py:58-61` (raises `RuntimeError` when the lifespan is inactive). It exposes `runtime.status()`, `runtime.targets()`, `runtime.catalog`, and `runtime.database.*` (`projects()`, `project()`, `jobs()`, `job()`, `events()`).
- Existing `openmcp://` resources at `server.py:189-246` already wrap these methods; reuse the same methods and the `_json` helper (`server.py:181-186`). Response models live in `models.py` (`ProjectView`, `JobView`, `TargetView`, `DaemonStatusResult`).
- Bind stays `127.0.0.1`, no auth (localhost single-user).
- Tests: pytest, `uv run pytest`; existing fixtures in `tests/conftest.py` and `tests/test_database.py` / `tests/test_server.py`.

## Files
- Create: `src/openmcp/dashboard.py`
- Create: `src/openmcp/dashboard_static/index.html`
- Create: `src/openmcp/dashboard_static/app.js`
- Create: `src/openmcp/dashboard_static/styles.css`
- Create: `src/openmcp/dashboard_static/vendor/alpine.min.js`
- Create: `tests/test_dashboard.py`
- Modify: `src/openmcp/server.py`

## Done When
- Each read endpoint returns the documented shape with `200`, and `404`/`503` on the error paths.
- `GET /dashboard` returns the SPA HTML; assets load from `/dashboard/assets/...`.
- Views render and auto-poll; polling stops when the tab is hidden.
- Existing MCP behavior on `/mcp` is unchanged.
- `uv run pytest tests/test_dashboard.py`
- `uv run pytest`
- `uv run openmcp doctor`

## Rules
Follow the supplied worker contract. Stay within scope: no write endpoints, no auth, no new transport, no CDN or build step (Alpine vendored locally). Maintain this phase's `notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
