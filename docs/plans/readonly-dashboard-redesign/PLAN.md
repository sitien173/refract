# Read-Only Dashboard Redesign Plan

**Design:** [DESIGN.md](DESIGN.md)
**Context key:** `readonly-dashboard-redesign`
**Base:** `refs/plans/readonly-dashboard-redesign/base` (`38f97c55`)
**Commit:** `feat(dashboard)!: replace dashboard with read-only live job console`

## Outcome & Scope

Replace the Refract dashboard with a fresh read-only split-pane live job console built on React 19, Vite, and TDS tokens. Remove every server path that existed only for UI configuration editing.

Preserved invariants: loopback client and Host guards on all `/dashboard/*` routes and `/ask`; `POST /ask` behavior; JSON 404 for unknown `/dashboard/api/*` paths and verbs; SQLite schema; Vite `base` and `outDir`; configuration reload through `Runtime.publish_configuration`.

Out of scope: configuration editing in any interface, job actions from the UI, a cross-project jobs endpoint, dark theme, MCP tool contract changes, the unrelated `worker-job-telemetry` plan.

## Baseline Evidence

- `cd server && uv run --no-sync pytest -q`: 1255 passed, 23 skipped, 15 deselected.
- `cd server && uv run pytest -q`: fails before tests run; `uv` sync gets HTTP 404 for `iniconfig-2.4.0` wheel. All plan commands use `--no-sync`.
- `cd server/web && npm test`: 22 files, 288 tests passed.
- `cd server/web && npm run build`: succeeds, but output differs from the committed bundle (`index-Dmt_vjdw.js` replaced by `index-CAh75ErS.js`). The committed static bundle is already stale at base. No test guards build drift; the test named by consultation does not exist.

### Phase 1: Read-only server API

**Task Guide Input:** Non-UI Python server change. Remove configuration mutation support and prune dashboard GET routes the new UI will not call, keeping read routes, SSE, loopback guards, and `/ask` intact. Update Python tests.
**Goal:** The server exposes only the read-only dashboard API contract in DESIGN.md, with no configuration mutation code.
**Invariants & Boundaries:** Keep `_loopback_route`, `_is_loopback_client`, `_is_loopback_host`, `/ask`, static and asset routes, and the JSON 404 catch-all. Keep `Runtime.publish_configuration`, `_publish_configuration_locked`, and `_ensure_fresh_configuration`. Do not touch `server/web/` or `dashboard_static/`. Do not change the SQLite schema or MCP tools.
**Files:**
- Delete: `server/src/refract/config_mutation.py`
- Delete: `server/tests/test_config_mutation.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/config.py`
- Modify: `server/pyproject.toml`
- Modify: `server/uv.lock`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_dashboard_consolidation.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_server.py`
**Tasks:**
1. Write failing tests first: deleted routes (`bootstrap`, `status`, `configuration`, `configuration/targets[/{id}]`, `configuration/profiles[/{id}]`, `projects/{id}/profile-overrides[/{id}]`, `task-guide`) return the JSON 404 for GET, POST, PUT, DELETE; `GET /dashboard/api/profiles` returns `default`, `available`, and `profiles` with `id`, `parent`, `declared`, `inherited`, `effective`, `sources` from `_profile_config_data`; recovery strings in `runtime.py` and `server.py` name `.refract/config.toml`.
2. Replace `Runtime.mutations` with a `threading.RLock` attribute and update the four `with self.mutations.lock:` sites. Delete `config_mutation.py`, `_publish_project_configuration_locked` if uncalled, `load_config_bytes` and the `data` parameter of `load_project_config` if uncalled, and dashboard-only task guide helpers if uncalled.
3. In `dashboard.py`, delete the target, profile, and project-override registrars, task-guide registrar, `bootstrap`, `status`, and `configuration` routes, CSRF and If-Match constants and helpers, `_mutation_error_response`, mutation and editor-read authorization helpers, and `ConfigurationMutationError` import. Remove `csrf_token` from `DashboardState` and its setup in `server.py`. Delete models in `models.py` left without references, and `DashboardError` fields used only by mutations.
4. Delete mutation-only tests, drop `csrf_token` from fixtures, update tests that called removed routes. Remove `tomlkit` from `pyproject.toml` and regenerate `uv.lock`.
**Acceptance Criteria:**
- No file under `server/src` or `server/tests` references `config_mutation`, `ConfigurationMutationService`, `tomlkit`, `csrf`, or `runtime.mutations`.
- `server/pyproject.toml` and `server/uv.lock` contain no `tomlkit` entry.
- Every route listed as kept in DESIGN.md still responds and still rejects non-loopback clients and hosts.
- Job submission through the runtime succeeds.
- Full server suite passes.
**Reviewer Checklist:**
- Loopback guards remain on every remaining route, including `/ask`.
- Lock replacement covers all four former `mutations.lock` sites and keeps reentrancy.
- No read route or helper still used by kept routes was deleted.
- No secret-bearing field such as `system_prompt` or raw target `args` is newly exposed by the enriched `profiles` response.
- `uv.lock` diff only removes `tomlkit`.
**Verification Checks:**
- `cd server && uv run --no-sync pytest -q`
- `cd server && ! grep -rnE 'config_mutation|ConfigurationMutation|tomlkit|csrf|\.mutations' src tests pyproject.toml uv.lock`

### Phase 2: New UI shell and live job console

**Task Guide Input:** UI and client implementation. Delete all old dashboard source under `server/web/src` and build a fresh React 19 app: shell, status strip, nav rail with project switcher, Live job feed, job inspector, and live virtualized transcript, styled with TDS semantic tokens and `tds-*` classes only, light theme. Use `tds rules`, `tds search`, `tds component`, and `tds tokens` before writing UI.
**Goal:** Opening `/dashboard/` shows the split-pane live console that streams the selected job transcript in real time.
**Invariants & Boundaries:** Call only endpoints kept in DESIGN.md. No new npm dependencies. Keep `vite.config.js` `base`, `outDir`, and test setup. No mutating controls. Do not reference or copy deleted source. Do not edit Python or `dashboard_static/`. Secondary views render placeholders only.
**Files:**
- Delete: every file under `server/web/src/` except `server/web/src/test/setup.js`
- Create: `server/web/src/main.jsx`
- Create: `server/web/src/App.jsx`
- Create: further modules and tests under `server/web/src/` for API client, hash router, polling, transcript stream, shell, status strip, nav rail, job feed, and inspector
- Modify: `server/web/index.html`
**Tasks:**
1. TDD the API client and data hooks: polling at 3 s for `overview`, 2 s for `projects/{id}/jobs` on the Live view, 2 s for `jobs/{id}` until terminal; pause when `document.visibilityState` is `hidden`; back off to 10 s and mark data stale when the API is unreachable.
2. TDD the transcript stream: at most one `EventSource`, only for the selected non-terminal job; page `output?after=` until `has_more` is false; close on job switch, view change, and terminal drain; reconnect with exponential backoff from the last cursor; merge `assistant.text_delta` by `entity_id`; pair `tool.started` and `tool.completed`; render lifecycle, `stream.truncated`, `stream.persistence_failed`, and `retained_from` notices; fall back to `result.text` when `stream_status` is unavailable.
3. TDD the shell and Live view: hash routes from DESIGN.md, status strip, config-invalid banner, project switcher persisted in `localStorage`, feed with active and recent sections and `more_recent` note, follow-newest-running toggle, inspector header with telemetry, failure card, and Transcript, Result, and Plan tabs with job-scoped diagnostics.
**Acceptance Criteria:**
- `server/web/src` contains no file from the base commit except `test/setup.js`.
- Tests cover every task behavior above and pass.
- Rendered markup contains no `form`, `input` other than filter and toggle controls, or button that sends a non-GET request.
- CSS uses only TDS semantic tokens; no hex colors or core tokens.
- `npm run build` succeeds.
**Reviewer Checklist:**
- `EventSource` lifecycle cannot leak across job switches or unmounts.
- No polling continues while hidden.
- TDS rules: light theme, semantic tokens, official `tds-*` classes only.
- Transcript virtualization handles thousands of events without full re-render.
- Accessibility: landmarks, keyboard navigation of feed and tabs.
**Verification Checks:**
- `cd server/web && npm test`
- `cd server/web && npm run build`
- `cd server/web && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|--color-' src --include=*.css`

### Phase 3: Secondary read-only views

**Task Guide Input:** UI and client implementation. Add Projects, Targets and profiles, Diagnostics, and Runtime views to the new dashboard, read-only, TDS tokens only.
**Goal:** Every nav rail item renders its read-only view from the kept endpoints.
**Invariants & Boundaries:** Same as Phase 2. Reuse Phase 2 hooks, router, and table patterns. No new endpoints or dependencies.
**Files:**
- Create: view modules and tests under `server/web/src/` for Projects, Targets and profiles, Diagnostics, and Runtime
- Modify: `server/web/src/App.jsx` and Phase 2 router or nav modules as needed
**Tasks:**
1. TDD Projects: project table; detail at `#/projects/:id` with global and project default profiles and per-workflow target chains with source attribution.
2. TDD Targets and profiles: target table with backend, model, isolation, read-only flag, active over max concurrency, breaker state, cooldown, probing; profile routing matrix from enriched `profiles`.
3. TDD Diagnostics and Runtime: diagnostics filters for project, category, job id, `before` cursor pagination, expandable expected and observed, links to `#/jobs/{job_id}`; Runtime with config health and daemon and logging settings.
**Acceptance Criteria:**
- Each view renders loading, empty, error, and populated states under test.
- Diagnostics pagination requests `before=<next_before>` and stops when `next_before` is null.
- `npm test` and `npm run build` pass.
**Reviewer Checklist:**
- No mutating controls.
- No duplicated fetch or polling logic outside Phase 2 hooks.
- TDS compliance as in Phase 2.
**Verification Checks:**
- `cd server/web && npm test`
- `cd server/web && npm run build`
- `cd server/web && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|--color-' src --include=*.css`

### Phase 4: Committed bundle and documentation

**Task Guide Input:** Build and documentation change. Rebuild the committed dashboard bundle, remove stale assets, and update docs for the read-only dashboard.
**Goal:** The committed `dashboard_static` matches a fresh build and docs describe the read-only dashboard.
**Invariants & Boundaries:** Do not change application source except fixes required for a reproducible build. Docs must not mention dashboard configuration editing.
**Files:**
- Modify: `server/src/refract/dashboard_static/` (full regenerated contents)
- Modify: `server/README.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
**Tasks:**
1. Run `npm run build`, commit the full regenerated bundle, and confirm old hashed assets and `flowforge-logo` asset are gone.
2. Rewrite the `server/README.md` dashboard sections, including "Admin Configuration Dashboard" and "Dashboard Management", to describe the read-only views and state that configuration changes go through `config.toml` and `.refract/config.toml`.
3. Add a `CHANGELOG.md` entry recording the breaking removal of dashboard write endpoints, removed GET routes, and `tomlkit`.
**Acceptance Criteria:**
- A second `npm run build` leaves `server/src/refract/dashboard_static` unchanged.
- `server/README.md` has no reference to dashboard editing, CSRF, or If-Match.
- Server and UI suites pass.
**Reviewer Checklist:**
- Bundle contains no old asset names from base.
- Changelog lists every removed route.
**Verification Checks:**
- `cd server/web && npm test`
- `cd server/web && h() { find ../src/refract/dashboard_static -type f | sort | xargs sha256sum | sha256sum; } && npm run build >/dev/null && a=$(h) && npm run build >/dev/null && [ "$a" = "$(h)" ]`
- `cd server/web && ! ls ../src/refract/dashboard_static/assets | grep -E 'Dmt_vjdw|N_5a6zmM|flowforge'`
- `cd server && uv run --no-sync pytest -q`
- `! grep -nEi 'csrf|if-match|edit.*dashboard|dashboard.*edit' server/README.md`
