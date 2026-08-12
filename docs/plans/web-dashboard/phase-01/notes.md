<!-- ccg-shared-version: 7.3.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Registered `/dashboard/api/status`, `/dashboard/api/projects`, `/dashboard/api/projects/{id}/jobs`, `/dashboard/api/jobs/{id}`, `/dashboard/api/jobs/{id}/events`, `/dashboard/api/targets`, and `/dashboard/api/profiles` using `@mcp.custom_route`.
- Wrapped `_active_runtime()` calls in try/except `RuntimeError` to return HTTP 503 when the daemon runtime is inactive.
- Used Starlette `JSONResponse` / `Response` with `_json` helper to format responses consistent with existing MCP resource endpoints.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  RED: `tests/test_dashboard.py` failed with 404 (routes not registered) and 503 verification when runtime inactive.
  GREEN: `uv run pytest tests/test_dashboard.py` returned 8 passed in 0.81s.
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Served `/dashboard` SPA index HTML via custom route returning `FileResponse(index_file, media_type="text/html")`.
- Mounted `StaticFiles` at `/dashboard/assets` on `mcp._custom_starlette_routes` to serve `styles.css`, `app.js`, and `vendor/alpine.min.js`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  RED: `GET /dashboard` and `GET /dashboard/assets/styles.css` returned 404.
  GREEN: `uv run pytest tests/test_dashboard.py` passed static route tests cleanly.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Vendored Alpine.js locally at `src/openmcp/dashboard_static/vendor/alpine.min.js` (no external CDN or build step required).
- Built tabbed single-page application with Overview (status tiles + target health grid + profiles), Jobs (state-filtered table + event timeline modal drawer), and Projects views.
- Implemented background polling (~3s overview/lists, ~2s active job details) with `visibilitychange` handler to pause when `document.hidden` is true and resume when visible.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: SPA static files verified via `GET /dashboard` and asset endpoints.
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- Added comprehensive unit tests in `tests/test_dashboard.py` covering all read-only API endpoints, static route serving, 503 error path when runtime is inactive, and 404 paths for unknown project/job IDs.
- Used `httpx.AsyncClient` with `ASGITransport` against `mcp.streamable_http_app()` to avoid SQLite thread affinity issues with Starlette TestClient synchronous worker threads.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_dashboard.py` passed 11/11 tests. Full test suite `uv run pytest` passed 80/80 tests. `uv run openmcp doctor` passed cleanly.
- Root cause (bugfix only): n/a
