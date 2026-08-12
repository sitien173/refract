# Web Dashboard & Monitor — Design

## Purpose

A local web UI that monitors the OpenMCP daemon and lets the operator edit
`config.toml` and task guidance through structured forms. Read-only for all
daemon state; the only mutations are the two config files.

## Confirmed constraints

- **Scope:** read-only monitoring + structured-form editing of
  `~/.openmcp/config.toml` and `~/.openmcp/task_guide.json`. No job
  submit/cancel/retry.
- **Users:** single operator, localhost only. No auth, bind stays `127.0.0.1`.
- **Freshness:** auto-poll refresh (no push/streaming).
- **Stack:** Python, in this repo. No JS build toolchain.
- **Editing UX:** structured forms with validation.

## Architecture (Approach A — in-process)

The dashboard runs inside the existing daemon process. The MCP server is
`FastMCP` (Starlette + uvicorn) on `127.0.0.1:8765`. Extra HTTP routes mount via
`@mcp.custom_route`, served by the same uvicorn. Handlers reach live daemon
state through the module global `_active_runtime()` (custom routes get a raw
Starlette `Request`, not an MCP `Context`).

Rejected: a separate sidecar web app (Approach B). More processes and plumbing
with no benefit at localhost single-user scale.

### New modules

- `src/openmcp/dashboard.py` — registers routes on the FastMCP server; request
  handlers. Wired from `server.py` setup.
- `src/openmcp/config_writer.py` — the only net-new write logic: serialize and
  atomically write `config.toml` / `task_guide.json`, validated by the daemon's
  own loaders before commit.
- `src/openmcp/dashboard_static/` — SPA assets (Alpine.js vendored locally, no
  build), served as static files.

### Backend endpoints

Read (GET, JSON; thin wrappers over `_active_runtime()`, reusing `models.py`
and the `_json` helper):

| Route | Source |
|---|---|
| `GET /dashboard/api/status` | `runtime.status()` |
| `GET /dashboard/api/projects` | `runtime.database.projects()` |
| `GET /dashboard/api/projects/{id}/jobs` | `runtime.database.jobs()` |
| `GET /dashboard/api/jobs/{id}` | `runtime.database.job()` |
| `GET /dashboard/api/jobs/{id}/events` | `runtime.database.events()` |
| `GET /dashboard/api/targets` | `runtime.targets()` (incl. health) |
| `GET /dashboard/api/profiles` | `runtime.catalog` |
| `GET /dashboard/api/config` | current parsed config, shaped for forms |
| `GET /dashboard/api/task-guide` | `load_task_guide(...)` |

Write:

- `PUT /dashboard/api/config` — validate → write → run reload path → return
  `restart_required`.
- `PUT /dashboard/api/task-guide` — validate → write.

Static:

- `GET /dashboard` serves the SPA; assets under `/dashboard/assets/...`.

Design rule: read endpoints reuse the same runtime methods the `openmcp://`
resources use, rather than duplicating query logic.

## Frontend

No build step. Alpine.js (~15KB) vendored into `dashboard_static/`, plus plain
`fetch`. No npm, bundler, or CDN — works offline.

Single page, tabbed views:

- **Overview** — status tiles (running, workers, active, queued) + targets
  health grid (healthy / circuit-open).
- **Jobs** — table (state, workflow, project, updated_at), filter by state; row
  opens a detail panel with result + events timeline.
- **Projects** — alias, root, head_commit, clean flag.
- **Config** — structured forms: daemon settings, targets list, profiles
  (workflow→target maps).
- **Task guide** — structured form for recommendations.

## Data flow

- Client `setInterval` + `fetch`. Status and list views poll ~3s; open job
  detail/events poll ~2s.
- Polling pauses when the tab is hidden (`visibilitychange`).
- Config and task-guide are fetched on demand, never polled — they are edit
  surfaces and repolling would clobber in-progress edits.

## Write flow

1. Form edit → client-side validation (required fields, types) → `PUT`.
2. Server re-validates via `load_config` / `load_task_guide`. On failure,
   respond `400` with the message; the live file is untouched.
3. On success: config write runs the reload path and returns `restart_required`;
   UI shows a banner when true, then refetches.

### Atomic, validated writes (`config_writer.py`)

1. Write proposed content to a temp file in `~/.openmcp/`.
2. Validate by running the real loader against the temp path
   (`load_config(tmp)` / `load_task_guide`).
3. On success, `os.replace()` temp → real file (atomic). On failure, delete
   temp, return `400`.
4. Keep the prior file as `config.toml.bak` / `task_guide.json.bak` before
   replace.

### TOML writer

Use **`tomlkit`** (new dependency) to round-trip `config.toml` and preserve the
operator's comments and formatting across form saves. Task guide is JSON —
stdlib `json`, no dependency.

## Errors and edge cases

- `_active_runtime()` unavailable (daemon starting/stopping) → `503`; UI shows
  "daemon not running."
- Unknown job/project id → `404`.
- Validation failure on write → `400`, message rendered inline in the form.
- **Editing config while a job runs is safe:** the daemon snapshots selection
  per job and reload affects only later submissions. Edits are not blocked on
  active jobs; the UI surfaces the active-job count for context.
- Non-hot-reloadable settings (host/port) → reload returns `restart_required`;
  UI banner says a manual restart is needed.
- Write paths are the two fixed files under `~/.openmcp/`; no user-supplied
  paths, so no traversal surface.

## Testing

- `config_writer` unit tests: valid write succeeds; invalid content rejected
  with the file untouched; atomic replace; `.bak` created; `tomlkit` preserves
  comments across a round-trip.
- Read-endpoint tests: build a `Runtime` on a temp DB (reuse existing
  fixtures); assert each endpoint's shape and status codes (`200`/`404`/`503`).
- Route integration via Starlette `TestClient`.
- Frontend: no JS test toolchain; manual smoke of each view and the write flow.
  Endpoint tests cover the contract.

## Rollout (phases, monitoring first)

1. **Phase 1 — Read-only monitor.** Read endpoints + static SPA shell +
   Overview/Jobs/Projects/Targets views + auto-poll. No write logic.
2. **Phase 2 — Config editing.** `config_writer` (+ `tomlkit`), Config forms,
   validate→write→reload→`restart_required` banner.
3. **Phase 3 — Task-guide editing.** JSON writer + task-guide form.

Each phase is independently usable.
