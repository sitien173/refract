# Web Dashboard & Monitor — Implementation Plan

Design: [DESIGN.md](DESIGN.md)

In-process web dashboard on the daemon's uvicorn (`127.0.0.1:8765`, no auth).
Read-only monitoring plus structured-form editing of `config.toml` and
`task_guide.json`. Approach A (in-process). Alpine.js vendored, no build.

Profiles are resolved at execution unless the operator pins one.

---

### Phase 1: Read-only monitor

**Task Guide Input:** Add a read-only web dashboard to the OpenMCP daemon. Mount
HTTP routes on the existing FastMCP server via `@mcp.custom_route` (served by the
same uvicorn on `127.0.0.1:8765`). Handlers read live state through the module
global `_active_runtime()` since custom routes receive a raw Starlette `Request`,
not an MCP `Context`. Serve a single-page Alpine.js SPA (vendored locally, no
build step) as static files, with Overview, Jobs, Projects, and Targets views
that auto-poll. Distinct use cases: (a) JSON read endpoints wrapping runtime
methods, reusing `models.py` and the `_json` helper; (b) static asset serving;
(c) a client-side SPA that polls and pauses when the tab is hidden.
**Profile:** `Resolve at execution`
**Goal:** Operator can watch daemon status, jobs, projects, and target health in a browser.

**Files:**
- Create: `src/openmcp/dashboard.py`
- Create: `src/openmcp/dashboard_static/index.html`
- Create: `src/openmcp/dashboard_static/app.js`
- Create: `src/openmcp/dashboard_static/styles.css`
- Create: `src/openmcp/dashboard_static/vendor/alpine.min.js`
- Create: `tests/test_dashboard.py`
- Modify: `src/openmcp/server.py`

**Tasks:**
1. In `dashboard.py`, register read endpoints via `@mcp.custom_route`:
   `GET /dashboard/api/status`, `/projects`, `/projects/{id}/jobs`, `/jobs/{id}`,
   `/jobs/{id}/events`, `/targets`, `/profiles`. Each resolves `_active_runtime()`,
   returns JSON from existing runtime/database methods, and maps a missing runtime
   to `503` and unknown ids to `404`.
2. Register static routes: `GET /dashboard` serves `index.html`; `/dashboard/assets/...`
   serves `dashboard_static`. Wire the registration from `server.py` setup.
3. Build the SPA: tabbed Overview (status tiles + targets health grid), Jobs
   (state-filtered table + detail panel with events), Projects list. Poll status
   and lists ~3s, open job detail ~2s, pause on `visibilitychange`.
4. Add `tests/test_dashboard.py` using Starlette `TestClient` against a `Runtime`
   on a temp DB (reuse existing fixtures).

**Acceptance Criteria:**
- Each read endpoint returns the documented shape with `200`, and `404`/`503` on the error paths.
- `GET /dashboard` returns the SPA HTML; assets load from `/dashboard/assets/...`.
- Views render and auto-poll; polling stops when the tab is hidden.
- The daemon's existing MCP behavior on `/mcp` is unchanged.

**Reviewer Checklist:**
- Custom routes use `_active_runtime()`, not an MCP `Context`.
- Read endpoints reuse runtime/database methods rather than duplicating query logic.
- No write endpoints, no auth surface beyond the existing localhost bind.
- Alpine is vendored locally; no CDN or build step introduced.

**Verification Checks:**
- `uv run pytest tests/test_dashboard.py`
- `uv run pytest`
- `uv run openmcp doctor`

**Commit:** `feat(dashboard): add read-only monitor UI and endpoints`

---

### Phase 2: Config editing

**Task Guide Input:** Add structured-form editing of `~/.openmcp/config.toml` to
the dashboard. Create `config_writer.py` that serializes daemon/targets/profiles
edits with `tomlkit` (new dependency) to preserve comments, writes to a temp file
under `~/.openmcp/`, validates by running `load_config` against the temp path,
keeps the prior file as `config.toml.bak`, then atomically `os.replace()`s into
place; on validation failure it deletes the temp file and returns the error. Add
`GET /dashboard/api/config` (parsed config shaped for forms) and
`PUT /dashboard/api/config` (validate → write → run the reload path → return
`restart_required`). Add Config form views. Editing while a job runs is safe and
must not be blocked; surface the active-job count. Distinct use cases: atomic
validated write, the reload/`restart_required` signal, and the structured form UI.
**Profile:** `Resolve at execution`
**Goal:** Operator edits config through validated forms and sees when a restart is required.

**Files:**
- Create: `src/openmcp/config_writer.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/dashboard_static/index.html`
- Modify: `src/openmcp/dashboard_static/app.js`
- Modify: `tests/test_dashboard.py`
- Modify: `pyproject.toml`

**Tasks:**
1. Add `tomlkit` to `pyproject.toml` dependencies.
2. Implement `config_writer.write_config`: temp write, `load_config(tmp)` validation,
   `.bak` backup, atomic replace; raise/return a clear error on invalid content.
3. Add `GET`/`PUT /dashboard/api/config`; `PUT` validates, writes, runs the reload
   path, and returns `restart_required`; validation failure → `400` with message.
4. Build the Config forms (daemon settings, targets list, profiles map) with
   client-side validation, inline server error display, restart-required banner,
   and an active-job-count indicator.

**Acceptance Criteria:**
- Valid edits persist; the live file is untouched on invalid input, and `.bak` holds the prior version.
- Comments in `config.toml` survive a form save (`tomlkit` round-trip).
- `PUT` returns `restart_required` correctly; the UI banner reflects it.
- Editing is available while a job is queued or running.

**Reviewer Checklist:**
- Writes are atomic and validated by the real `load_config`, not reimplemented rules.
- No path input beyond the fixed `~/.openmcp/config.toml`; no traversal surface.
- Reload affects only later submissions; running jobs are not disturbed.

**Verification Checks:**
- `uv run pytest tests/test_dashboard.py`
- `uv run pytest`

**Commit:** `feat(dashboard): add validated config editing`

---

### Phase 3: Task-guide editing

**Task Guide Input:** Add structured-form editing of the task guidance file
(`~/.openmcp/task_guide.json`, or per-project `.openmcp/task_guide.json`) to the
dashboard. Reuse the atomic validated-write pattern from `config_writer.py` but
serialize with stdlib `json` and validate with `load_task_guide` (must be a
non-empty object). Add `GET /dashboard/api/task-guide` and
`PUT /dashboard/api/task-guide`, and a task-guide form view with a
`task_guide.json.bak` backup on write. Distinct use cases: JSON read of the
current guide, atomic validated JSON write, and the form UI.
**Profile:** `Resolve at execution`
**Goal:** Operator edits task guidance through a validated form.

**Files:**
- Modify: `src/openmcp/config_writer.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/dashboard_static/index.html`
- Modify: `src/openmcp/dashboard_static/app.js`
- Modify: `tests/test_dashboard.py`

**Tasks:**
1. Add `config_writer.write_task_guide`: temp write, `load_task_guide` validation,
   `task_guide.json.bak` backup, atomic replace.
2. Add `GET`/`PUT /dashboard/api/task-guide`; `PUT` validates and writes, `400` on failure.
3. Build the task-guide form (recommendations) with client-side validation and inline errors.

**Acceptance Criteria:**
- Valid guidance persists; invalid (empty/non-object) rejected with the file untouched.
- `.bak` holds the prior version after a write.
- The form loads current guidance and saves edits.

**Reviewer Checklist:**
- Empty/non-object payloads are rejected via `load_task_guide`, not custom rules.
- Home vs per-project path handling matches `load_task_guide` resolution.

**Verification Checks:**
- `uv run pytest tests/test_dashboard.py`
- `uv run pytest`

**Commit:** `feat(dashboard): add validated task-guide editing`
