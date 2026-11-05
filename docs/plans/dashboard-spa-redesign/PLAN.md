# Dashboard SPA Redesign Plan

**Design:** [DESIGN.md](DESIGN.md)
**Context key:** `dashboard-spa-redesign`
**Base:** `refs/plans/dashboard-spa-redesign/base` (`46714b4a87e138abc47076ba0d810563e8ed4874`)
**Commit:** `feat(dashboard)!: rebuild dashboard as a TDS-styled React console with job actions`

## Outcome & Scope

Replace the server-rendered dashboard with a React, Vite, TypeScript, Tailwind v4, and shadcn/ui single-page console styled with TDS. Add a bounded `/dashboard/api` JSON surface, live filtered job list, readable transcript, split-pane layout, and cancel, retry, and answer actions behind a CSRF guard.

Preserved invariants:

- Every dashboard route and `/ask` stay behind `_loopback_route` (`server/src/refract/dashboard.py:90`).
- The six MCP tools and `/ask` keep their schema and behavior. `tests/test_mcp_schema_contract.py` and the `/ask` tests in `tests/test_dashboard.py` pass unchanged.
- No config editing. No database schema change.
- Light theme only. TDS semantic tokens only for color, type, and component look.

Out of scope: dark theme, config mutation, authentication or remote access, mobile-first layout below tablet width, telemetry views, a retry target override in the UI, and the Claude `complete_tool` status debt.

## Baseline Evidence

Commands run at plan base `46714b4a`:

- `cd /home/ngosi/projects/refract/server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider`: 1 failed, 781 passed, 15 deselected in 423.74 s. The failure is `tests/test_transport.py::test_timeout_kills_the_whole_process_group`. The log shows `python subprocess ended class=timeout after 0.64s`.
- `cd /home/ngosi/projects/refract/server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_transport.py::test_timeout_kills_the_whole_process_group`: passed 3 of 3 runs in isolation. Phase 1 repairs this baseline.
- `cd /home/ngosi/projects/refract/server && uv build --wheel -o /tmp/refract-wheel-base`: built `refract-2.4.0-py3-none-any.whl`, which contains `refract/dashboard_static/tds/*.css` and no `dashboard_static/app/`.
- Frontend commands do not exist at base. `server/web/` holds only ignored `node_modules/` and `coverage/`. Phase 3 creates `npm run typecheck`, `npm test`, `npm run build`, and `npm run check:bundle`; they are gates from Phase 3 onward.
- Toolchain at base: Node `v24.18.0`, npm `11.16.0`, Python `3.12.13`.

Shared command aliases used below:

- `PYTEST` = `cd /home/ngosi/projects/refract/server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider`
- `WEB` = `cd /home/ngosi/projects/refract/server/web`

### Phase 1: Trustworthy baseline and secure job actions

**Task Guide Input:** Backend repository change in Python. Use cases: fix a timing race in a transport test; add a CSRF-guarded JSON action API for cancel, retry, and answer; add question-ID matching to the ask registry without changing MCP behavior.
**Goal:** The full pytest suite passes reliably, and the three dashboard action endpoints exist with CSRF protection and race-safe answers.
**Invariants & Boundaries:** Do not change `_loopback_route` behavior for existing routes. Do not change `/ask`, the MCP `answer`, `cancel`, or `retry` tools, or their schemas. Do not touch the HTML page renderers. The transport fix changes test code or fake fixtures only, unless the root cause proves to be in `server/src/refract/backends/_process.py`; in that case, report it before changing production code.
**Files:**
- Modify: `server/tests/test_transport.py`
- Modify: `server/tests/fixtures/fake_cli/spawn_and_sleep.py` (only if the root cause is there)
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/src/refract/ask.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/tests/test_ask.py`
- Create: `server/tests/test_dashboard_api.py`
**Tasks:**
1. Use systematic-debugging to find the root cause of the `test_timeout_kills_the_whole_process_group` failure under full-suite load. Fix it so the test waits for the grandchild PID deterministically, not by a fixed timing guess.
2. Write failing tests, then add an optional `expected_question_id` argument to `AskRegistry.deliver_answer` (`server/src/refract/ask.py:199`) and `Runtime.job_answer` (`server/src/refract/runtime.py:423`). A mismatch returns `invalid_state`. The MCP path omits the argument.
3. Write failing tests, then add a CSRF guard and the routes `POST /dashboard/api/jobs/{id}/cancel`, `/retry`, and `/answer`. They call `Runtime.cancel`, `Runtime.retry`, and `Runtime.job_answer`. Responses use the `_error` shape with status codes 400, 403, 404, 409, and 503, plus `Cache-Control: no-store`.
**Acceptance Criteria:**
- The full suite passes, and the transport test file passes 20 consecutive runs.
- A POST is rejected with 403 when `Origin` is missing, is `null`, is foreign, or has a mismatched port; when `X-Refract-Dashboard` is missing; or when `Sec-Fetch-Site` is `cross-site`. A non-JSON content type returns 400 or 415.
- A valid POST to cancel a queued job returns success with state `cancelled`. Cancelling a running job may return state `running`.
- Retry returns a new job ID different from the source job ID.
- Answer with a stale `question_id` returns 409 and leaves the pending question in place. The MCP `answer` tool without a question ID still delivers.
- `tests/test_mcp_schema_contract.py` and the existing `/ask` tests pass unchanged.
**Reviewer Checklist:**
- The transport fix addresses the race; it does not just raise the timeout or skip the test.
- CSRF compares scheme, host, and port exactly. No CORS headers are added.
- No ask token, future, deadline, or execution plan is serialized.
- `expected_question_id` matching happens under the registry lock.
- Action routes are wrapped by `_loopback_route`.
**Verification Checks:**
- `PYTEST`
- `cd /home/ngosi/projects/refract/server && for i in $(seq 20); do PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_transport.py || exit 1; done`
- `PYTEST tests/test_dashboard_api.py tests/test_ask.py tests/test_dashboard.py tests/test_mcp_schema_contract.py`

### Phase 2: Read API with bounded queries

**Task Guide Input:** Backend repository change in Python. Use cases: a summary-only filtered and paginated job list query; a job detail object; a bounded output reader with `has_more`; targets JSON.
**Goal:** The SPA can read every page's data through `/dashboard/api` without loading result files for the list or reading whole stream files.
**Invariants & Boundaries:** No database schema change. Keep the line-number `seq` cursor. Keep the existing HTML routes and `GET /dashboard/jobs/{id}/output` working until Phase 5. Do not change `database.jobs()` callers outside the dashboard.
**Files:**
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `server/tests/test_database.py`
**Tasks:**
1. Write failing tests, then add a summary SQL query with filters for state, project, workflow, target, and job-ID search, applied before cursor pagination. It must not call `result_path(...).read_text`. Expose it as `GET /dashboard/api/jobs` with filter options.
2. Write failing tests, then add `GET /dashboard/api/jobs/{id}` returning allowlisted job fields, prompt, result, project root, and `pending_question {question_id, text}` or null.
3. Write failing tests, then add `GET /dashboard/api/jobs/{id}/output?after=N` returning `{events, next, has_more, available, state, terminal}` with a bounded reader, and `GET /dashboard/api/targets` returning targets and config health.
**Acceptance Criteria:**
- The list endpoint applies every filter before pagination and returns a working cursor.
- A test proves the list path reads no result files.
- Output with 1200 events returns 500, then 500, then 200, with `has_more` true, true, false.
- A partial final line is withheld. A missing stream file returns empty events with `available: false`.
- Detail never contains the keys `token`, `future`, `deadline`, or `execution_plan`.
- Every new route is loopback-guarded and an unknown `/dashboard/api/*` path returns a JSON 404.
**Reviewer Checklist:**
- SQL uses bound parameters only.
- The output reader does not load the whole file into memory.
- JSON keys match DESIGN.md exactly.
**Verification Checks:**
- `PYTEST`
- `PYTEST tests/test_dashboard_api.py tests/test_database.py tests/test_dashboard.py`

### Phase 3: Frontend foundation and bundle pipeline

**Task Guide Input:** Frontend and client change, plus CI. Use cases: scaffold Vite, React, TypeScript, Tailwind v4, and shadcn/ui under `server/web`; bridge shadcn variables to TDS tokens; serve the SPA shell and assets from the server; enforce a committed, reproducible bundle in CI.
**Goal:** `/dashboard/*` can serve a built TDS-styled SPA shell, and CI fails when the committed bundle is stale.
**Invariants & Boundaries:** Follow the shadcn/ui plus TDS rules: TDS classes and semantic tokens for look, Tailwind for layout only with TDS token values, no `.dark` or `@custom-variant dark`, TDS CSS imported with `layer(components)`, Tailwind default color and radius theme cleared. Verify library APIs and versions with `ctx7` before use. The existing HTML pages keep serving `/dashboard`, `/dashboard/jobs/{id}`, and `/dashboard/targets` until Phase 5; mount the SPA shell at a preview path `/dashboard/app/*` for this phase. Vite empties only `server/src/refract/dashboard_static/app/`.
**Files:**
- Create: `server/web/package.json`, `server/web/package-lock.json`, `server/web/.nvmrc`
- Create: `server/web/index.html`, `server/web/vite.config.ts`, `server/web/tsconfig.json`, `server/web/components.json`
- Create: `server/web/src/main.tsx`, `server/web/src/App.tsx`
- Create: `server/web/src/styles/globals.css`, `server/web/src/styles/tds/*.css`
- Create: `server/web/src/components/ui/*.tsx` for Button, Select, Input, Tabs, Dialog, AlertDialog, Resizable
- Create: `server/web/src/test/setup.ts`, `server/web/src/styles/tokens.test.tsx`
- Create: `server/web/scripts/check-bundle.mjs`
- Create: `server/src/refract/dashboard_static/app/**` (build output)
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_dashboard_api.py`
- Modify: `.github/workflows/server.yml`
**Tasks:**
1. Scaffold the app with npm scripts `dev`, `build`, `typecheck` (`tsc --noEmit`), `test` (Vitest), and `check:bundle`. Copy TDS CSS from `server/src/refract/dashboard_static/tds/` and fetch any extra components with `tds component <id>`. Write the token bridge in `globals.css` per the AGENTS.md table.
2. Add shadcn components with TDS classes. Write Vitest checks that computed colors and radius on Button and on portalled Dialog and Select content resolve to TDS token values.
3. Write failing pytest tests, then serve the shell with an index fallback and hashed assets under the preview path. A missing asset returns 404.
4. Write `check-bundle.mjs` to build into a temporary directory and compare every file name and byte with `dashboard_static/app/`. Add a `web` job to `server.yml` on `ubuntu-latest` using the `.nvmrc` Node version, `npm ci`, typecheck, test, and `check:bundle`.
**Acceptance Criteria:**
- `npm run typecheck`, `npm test`, and `npm run check:bundle` pass from a clean `npm ci`.
- Editing any source file without rebuilding makes `check:bundle` exit non-zero. Deleting or adding a file in `dashboard_static/app/` also fails it.
- `GET /dashboard/app/` and `GET /dashboard/app/jobs/x` return the shell. A missing asset returns 404.
- The built wheel contains `refract/dashboard_static/app/index.html`.
- No dark-mode selectors and no hardcoded hex colors in `server/web/src`.
**Reviewer Checklist:**
- No Tailwind color, font, or radius utilities in components. Layout utilities use TDS token values.
- No circular CSS variable references such as `--radius: var(--radius-card)`.
- Radix keyboard and focus behavior is intact.
- The `web` CI job is a required dependency of `release.yml` through `server.yml`.
**Verification Checks:**
- `WEB && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle`
- `PYTEST tests/test_dashboard_api.py tests/test_dashboard.py`
- `cd /home/ngosi/projects/refract/server && rm -rf /tmp/refract-wheel && uv build --wheel -o /tmp/refract-wheel && unzip -l /tmp/refract-wheel/*.whl | grep -q 'refract/dashboard_static/app/index.html'`
- `cd /home/ngosi/projects/refract/server/web/src && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|\.dark\b|custom-variant dark' --include='*.css' --include='*.tsx' .`

### Phase 4: Console features

**Task Guide Input:** Frontend and client change. Use cases: split-pane job console with URL state; live polling with filters and search; transcript reducer and viewer; targets view; cancel, retry, and answer UI.
**Goal:** The preview SPA reaches feature parity with the current pages and adds every confirmed enhancement.
**Invariants & Boundaries:** Read only through `/dashboard/api`. Send POSTs with `X-Refract-Dashboard` and `Content-Type: application/json`. Never render raw HTML from events. Do not invent timestamps or tool output. Sentence case for all UI text. No new runtime dependencies beyond those added in Phase 3 without stating why.
**Files:**
- Create: `server/web/src/api.ts`, `server/web/src/api.test.ts`
- Create: `server/web/src/hooks/usePolling.ts`, `server/web/src/hooks/usePolling.test.tsx`
- Create: `server/web/src/hooks/useJobOutput.ts`, `server/web/src/hooks/useJobOutput.test.tsx`
- Create: `server/web/src/router.ts`, `server/web/src/router.test.ts`
- Create: `server/web/src/transcript/reduce.ts`, `server/web/src/transcript/reduce.test.ts`, `server/web/src/transcript/fixtures/*.json`
- Create: `server/web/src/views/ConsoleView.tsx`, `server/web/src/views/TargetsView.tsx` and their tests
- Create: `server/web/src/components/JobList.tsx`, `JobFilters.tsx`, `JobDetail.tsx`, `TranscriptView.tsx`, `JobActions.tsx` and their tests
- Modify: `server/web/src/App.tsx`
- Modify: `server/src/refract/dashboard_static/app/**` (rebuilt)
**Tasks:**
1. Write failing tests, then build `api.ts`, `usePolling`, and `useJobOutput`: about 1 s interval, no overlapping requests, stale response discard on selection change, pause while hidden, about 5 s backoff on error, `has_more` drain after the job ends.
2. Write failing tests, then build the transcript reducer and viewer using fixtures recorded from Codex, Claude, Pi, and agy event shapes in `server/src/refract/backends/`. Group by attempt and entity, merge text deltas, pair tool events, show a fallback row for unknown kinds, and render a bounded window with a show-earlier control.
3. Write failing tests, then build the split-pane console, filters and search in the query string, selected job in the path, the targets view, and the action UI: AlertDialog to confirm cancel, "Cancellation requested" state, retry selects the new job, answer dialog sends `question_id`, and results show as TDS announcements.
4. Rebuild the bundle.
**Acceptance Criteria:**
- Every action button is disabled while its request is in flight.
- A hostile event string such as `<img src=x onerror=alert(1)>` renders as text.
- Reloading a deep link restores the selected job and filters.
- `npm run check:bundle` passes after the rebuild.
**Reviewer Checklist:**
- Polling cannot leak intervals or overlap after unmount or selection change.
- Labels and icon-only buttons meet TDS Rule 9.
- No raw `dangerouslySetInnerHTML`.
**Verification Checks:**
- `WEB && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle`
- `PYTEST tests/test_dashboard_api.py tests/test_dashboard.py`
- `cd /home/ngosi/projects/refract/server/web/src && ! grep -rn 'dangerouslySetInnerHTML' .`

### Phase 5: Cutover, documentation, and acceptance

**Task Guide Input:** Backend, CI, and documentation change, plus acceptance testing. Use cases: move the SPA from the preview path to `/dashboard/*`; delete the HTML renderers and vendored server-side TDS CSS; migrate tests; update README and CHANGELOG; run manual acceptance.
**Goal:** `/dashboard`, `/dashboard/jobs/{id}`, and `/dashboard/targets` serve the SPA, the old HTML dashboard code is gone, and acceptance evidence is recorded.
**Invariants & Boundaries:** `/ask` and its tests stay unchanged. Six-tool schema tests stay unchanged. Remove only code made dead by the cutover.
**Files:**
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/web/vite.config.ts`
- Modify: `server/src/refract/dashboard_static/app/**` (rebuilt)
- Delete: `server/src/refract/dashboard_static/tds/*.css`
- Modify: `server/tests/test_dashboard.py`, `server/tests/test_dashboard_api.py`
- Modify: `README.md`, `CHANGELOG.md`
- Modify: `docs/plans/dashboard-spa-redesign/phase-05/notes.md` (acceptance record)
**Tasks:**
1. Write failing tests, then serve the shell at `/dashboard/*` with API and asset routes registered first. Remove `_job_list`, `_job_detail`, `_job_output`, `_targets`, `_POLL_SCRIPT`, `_stylesheet`, `_page`, `_table`, `_tag`, and `GET /dashboard/jobs/{id}/output`. Replace HTML assertions in `tests/test_dashboard.py` with shell, deep-link, and asset tests.
2. Update the README dashboard section and add a `CHANGELOG.md` Unreleased entry listing added and removed routes.
3. Run manual acceptance with `playwright-cli --extension=brave` against a running daemon: deep links, keyboard navigation of list, tabs, and dialogs, live updates within 2 s on a real job, and each action. Record the TDS Rule 10 checklist from `tds rules` with pass or fail per item.
**Acceptance Criteria:**
- `GET /dashboard`, `/dashboard/jobs/{id}`, and `/dashboard/targets` return the SPA shell. `GET /dashboard/api/nope` returns a JSON 404.
- `grep -n '_POLL_SCRIPT\|_stylesheet\|dashboard_static/tds' -r server/src` finds nothing.
- The wheel contains `dashboard_static/app/index.html` and no `dashboard_static/tds/`.
- The acceptance record lists each TDS Rule 10 item as passing.
**Reviewer Checklist:**
- No orphaned imports or helpers in `dashboard.py`.
- CHANGELOG lists every added and removed route exactly.
- The acceptance record states real observed results, not expected ones.
**Verification Checks:**
- `PYTEST`
- `WEB && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle`
- `cd /home/ngosi/projects/refract/server && rm -rf /tmp/refract-wheel && uv build --wheel -o /tmp/refract-wheel && unzip -l /tmp/refract-wheel/*.whl | grep -q 'refract/dashboard_static/app/index.html' && ! unzip -l /tmp/refract-wheel/*.whl | grep -q 'dashboard_static/tds/'`
- `cd /home/ngosi/projects/refract && ! grep -rn '_POLL_SCRIPT\|_stylesheet\|dashboard_static/tds' server/src`
