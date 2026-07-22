## Original User Request
Build an in-process web dashboard and monitor for the OpenMCP daemon with config and task-guide editing.

## Phase
Phase 3 — Task-guide editing: operator edits `~/.openmcp/task_guide.json` through a validated structured form in the dashboard. Reuses the atomic validated-write pattern from config_writer.

## Tasks
- task-1: Add `config_writer.write_task_guide`: temp write to `~/.openmcp/`, validate via `load_task_guide`, `task_guide.json.bak` backup, atomic `os.replace()`.
- task-2: Add `GET /dashboard/api/task-guide` (current guide) and `PUT /dashboard/api/task-guide` (validate → write → 400 on failure) to `src/openmcp/dashboard.py`.
- task-3: Build task-guide form in the SPA with client-side validation and inline error display. Modify `index.html` and `app.js`.

## Context
- Task guide lives at `~/.openmcp/task_guide.json` (home) or per-project `.openmcp/task_guide.json`. `load_task_guide()` in `src/openmcp/config.py` resolves the path.
- Atomic write pattern established in `config_writer.py` (Phase 2). Serialize with stdlib `json`, validate with `load_task_guide` (must be non-empty object).
- Dashboard routes follow same pattern as Phase 2 config endpoints.
- `_active_runtime()` for runtime access, `_json_response()` helper, lazy imports inside `register_dashboard_routes()`.

## Files
- Modify: `src/openmcp/config_writer.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/dashboard_static/index.html`
- Modify: `src/openmcp/dashboard_static/app.js`
- Modify: `tests/test_dashboard.py`

## Done When
- Valid guidance persists; invalid (empty/non-object) rejected with file untouched.
- `.bak` holds prior version after write.
- Form loads current guidance and saves edits.
- `uv run pytest tests/test_dashboard.py`
- `uv run pytest`
- `uv run openmcp doctor`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
