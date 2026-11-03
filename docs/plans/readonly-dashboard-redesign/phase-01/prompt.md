# Phase 1: Read-only server API

## Goal & Outcome
- Plan Goal: Replace the Refract dashboard with a read-only live job console and remove every server path that existed only for UI configuration editing.
- Phase Outcome: The server exposes only the read-only dashboard API contract in `docs/plans/readonly-dashboard-redesign/DESIGN.md` and contains no configuration mutation code, no CSRF or If-Match handling, and no `tomlkit` dependency.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/readonly-dashboard-redesign/phase-01/base`
- Prior State: Baseline at plan base `38f97c55`. No phase has run. Read `docs/plans/readonly-dashboard-redesign/DESIGN.md` (sections "Read-Only API Contract" and "Server Removals") and `docs/plans/readonly-dashboard-redesign/PLAN.md` (Phase 1) first.
- Code Context:
  - `server/src/refract/runtime.py`: `self.mutations = ConfigurationMutationService(self)` at line 105; `with self.mutations.lock:` at lines 353, 623, 654, 711; `_publish_project_configuration_locked` at line 721; import at line 20. Recovery string near line 377.
  - `server/src/refract/dashboard.py`: imports `ConfigurationMutationError` (line 25); `DashboardState.csrf_token` (line 67); CSRF helpers near line 486; `bootstrap` route near line 514; `runtime.mutations.*` calls at lines 575 to 828 inside the target, profile, and project-override registrars.
  - `server/src/refract/server.py`: `state.csrf_token` set at lines 922 and 935. Recovery string near line 632.
  - `server/src/refract/models.py`: `csrf_token` field at line 332 (bootstrap model); editor and bootstrap models.
  - `server/src/refract/config.py`: `load_config_bytes` at line 766 and the `data` parameter of `load_project_config`.
  - `_profile_config_data` already exists; reuse it for the enriched `GET /dashboard/api/profiles`.

## Invariants & Boundaries
- Preserve: `_loopback_route`, `_is_loopback_client`, `_is_loopback_host`; `POST /ask` behavior; static and asset routes; the JSON 404 catch-all for unknown `/dashboard/api/*` paths and verbs; `Runtime.publish_configuration`, `_publish_configuration_locked`, `_ensure_fresh_configuration`; SQLite schema; MCP tool contract.
- Kept routes (all GET, all loopback-guarded): `overview`, `settings`, `targets`, `profiles`, `projects`, `projects/{project_id}`, `projects/{project_id}/jobs`, `jobs/{job_id}`, `jobs/{job_id}/output`, `jobs/{job_id}/output/updates`, `diagnostics`.
- Deleted routes: `bootstrap`, `status`, `configuration`, `configuration/targets[/{id}]`, `configuration/profiles[/{id}]`, `projects/{id}/profile-overrides[/{id}]`, `task-guide`, and every POST, PUT, DELETE under `/dashboard/api/*`.
- The enriched `profiles` response must not expose `system_prompt` or raw target `args`.
- Out of Scope: `server/web/`, `server/src/refract/dashboard_static/`, docs, README, CHANGELOG, later phases.

## Files
Allowed production and test paths:
- `server/src/refract/config_mutation.py` (delete)
- `server/tests/test_config_mutation.py` (delete)
- `server/src/refract/runtime.py` (modify: replace `mutations` with a `threading.RLock`, delete `_publish_project_configuration_locked` if uncalled, fix recovery string)
- `server/src/refract/dashboard.py` (modify: delete removed routes, registrars, CSRF and If-Match helpers, mutation error helper, mutation and editor-read authorization helpers, `ConfigurationMutationError` import, `csrf_token`; enrich `profiles`)
- `server/src/refract/server.py` (modify: remove `csrf_token` setup, fix recovery string)
- `server/src/refract/models.py` (modify: delete models and `DashboardError` fields left unreferenced)
- `server/src/refract/config.py` (modify: delete `load_config_bytes` and the `data` parameter of `load_project_config` if uncalled)
- `server/pyproject.toml` (modify: remove `tomlkit`)
- `server/uv.lock` (modify: regenerate; diff must only remove `tomlkit`)
- `server/tests/test_dashboard.py`, `server/tests/test_dashboard_consolidation.py`, `server/tests/test_runtime.py`, `server/tests/test_server.py` (modify)

Worker-owned phase records:
- `docs/plans/readonly-dashboard-redesign/phase-01/notes.md` (append `## Task <M>` blocks)
- `docs/plans/readonly-dashboard-redesign/phase-01/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, `server/web/`, `dashboard_static/`, or secrets.
- Run every Python command with `uv run --no-sync`. Plain `uv run` fails on a wheel 404 for `iniconfig-2.4.0`. For `uv.lock`, remove the `tomlkit` entries by hand or use `uv lock` only if it works offline without touching other packages; confirm the diff removes only `tomlkit`.

## Tasks
- task-1: Write failing tests first. Deleted routes return the JSON 404 for GET, POST, PUT, DELETE. `GET /dashboard/api/profiles` returns `default`, `available`, and `profiles`, each profile with `id`, `parent`, `declared`, `inherited`, `effective`, `sources` taken from `_profile_config_data`. Recovery strings in `runtime.py` and `server.py` name `.refract/config.toml`. Job submission through the runtime succeeds without `runtime.mutations`. Record RED evidence (assertion failures, not import errors).
- task-2: Replace `Runtime.mutations` with a `threading.RLock` attribute and update the four `with self.mutations.lock:` sites, keeping reentrancy. Delete `config_mutation.py`, `_publish_project_configuration_locked` if uncalled, `load_config_bytes` and the `data` parameter of `load_project_config` if uncalled, and dashboard-only task guide helpers if uncalled.
- task-3: In `dashboard.py`, delete the target, profile, and project-override registrars, the task-guide registrar, `bootstrap`, `status`, and `configuration` routes, CSRF and If-Match constants and helpers, `_mutation_error_response`, mutation and editor-read authorization helpers, and the `ConfigurationMutationError` import. Remove `csrf_token` from `DashboardState` and its setup in `server.py`. Delete models in `models.py` left without references, and `DashboardError` fields used only by mutations. Confirm each deletion has no remaining reference first.
- task-4: Delete mutation-only tests, drop `csrf_token` from fixtures, update tests that called removed routes. Remove `tomlkit` from `pyproject.toml` and `uv.lock`.

## Done When
- No file under `server/src` or `server/tests` references `config_mutation`, `ConfigurationMutationService`, `tomlkit`, `csrf`, or `runtime.mutations`.
- `server/pyproject.toml` and `server/uv.lock` contain no `tomlkit` entry, and the `uv.lock` diff only removes `tomlkit`.
- Every kept route still responds and still rejects non-loopback clients and hosts, including `/ask`.
- Job submission through the runtime succeeds.
- Run from `/home/ngosi/projects/refract`:
  - `cd server && uv run --no-sync pytest -q` (Baseline: 1255 passed, 23 skipped, 15 deselected; the count of passed tests will fall as mutation tests are deleted and rise as new tests are added)
  - `cd server && ! grep -rnE 'config_mutation|ConfigurationMutation|tomlkit|csrf|\.mutations' src tests pyproject.toml uv.lock`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/readonly-dashboard-redesign/phase-01/journal.md`, then return that block and the matching status line from `erp.md`.
