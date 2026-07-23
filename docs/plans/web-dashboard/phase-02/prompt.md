## Original User Request
Build an in-process web dashboard and monitor for the OpenMCP daemon with config and task-guide editing.

## Phase
Phase 2 — Config editing: operator edits `~/.openmcp/config.toml` through validated structured forms in the dashboard. Atomic validated writes with `tomlkit` to preserve comments.

## Tasks
- task-1: Add `tomlkit` to `pyproject.toml` dependencies.
- task-2: Implement `src/openmcp/config_writer.py` with `write_config`: temp write to `~/.openmcp/`, validate via `load_config(tmp)`, `.bak` backup, atomic `os.replace()`; raise/return clear error on invalid content.
- task-3: Add `GET /dashboard/api/config` (parsed config shaped for forms) and `PUT /dashboard/api/config` (validate → write → run reload path → return `restart_required`; validation failure → `400` with message) to `src/openmcp/dashboard.py`.
- task-4: Build Config forms in the SPA (daemon settings, targets list, profiles map) with client-side validation, inline server error display, `restart_required` banner, and active-job-count indicator. Modify `index.html` and `app.js`.

## Context
- Config lives at `~/.openmcp/config.toml`. `load_config()` in `src/openmcp/config.py` parses it.
- Dashboard routes are registered in `src/openmcp/dashboard.py:register_dashboard_routes()` via `@mcp.custom_route`. Imports from `openmcp.server` are inside the function (lazy, avoids circular import).
- `tomlkit` must be added to `pyproject.toml` dependencies. No other new deps.
- Atomic write pattern per DESIGN.md: write to temp file under `~/.openmcp/`, validate with real loader, `os.replace()` on success, `.bak` backup.
- Reload path: after successful write, call the daemon's reload mechanism. Return `restart_required` if non-hot-reloadable settings changed.
- Config editing while jobs run is safe — daemon snapshots per job, reload only affects later submissions. Surface active-job count in UI.
- Existing `_active_runtime()` pattern from Phase 1. `_json_response()` helper available.

## Files
- Create: `src/openmcp/config_writer.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/dashboard_static/index.html`
- Modify: `src/openmcp/dashboard_static/app.js`
- Modify: `tests/test_dashboard.py`
- Modify: `pyproject.toml`

## Done When
- Valid edits persist; live file untouched on invalid input, `.bak` holds prior version.
- Comments in `config.toml` survive a form save (`tomlkit` round-trip).
- `PUT` returns `restart_required` correctly; UI banner reflects it.
- Editing is available while a job is queued or running.
- `uv run pytest tests/test_dashboard.py`
- `uv run pytest`
- `uv run openmcp doctor`

## Rules
Follow the supplied worker contract. Stay within scope: no new transport, no auth, no job submit/cancel/retry from dashboard. Maintain this phase's `notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
