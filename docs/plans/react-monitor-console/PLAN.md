# PLAN: OpenMCP Monitor & Debug Console (React + Vite)

Design: [DESIGN.md](DESIGN.md)

Replace the Alpine.js static dashboard with a React + Vite + TypeScript app,
redesigned in the Flowforge product shell, scoped to monitor + debug only.
Frontend-only; the committed Vite build is served unchanged by the existing
FastMCP `/dashboard` route and `/dashboard/assets` mount.

## Contract facts (verified)

- `/dashboard` serves `src/openmcp/dashboard_static/index.html` via FileResponse.
- `/dashboard/assets` is a StaticFiles mount over `src/openmcp/dashboard_static/`.
  So a URL `/dashboard/assets/<p>` maps to `dashboard_static/<p>`.
- Vite `base: '/dashboard/assets/'` + default `assets/` dir yields asset URLs
  `/dashboard/assets/assets/<hash>.js` → `dashboard_static/assets/<hash>.js`. ✓
- Read-only GET endpoints (all consumed): `status`, `projects`,
  `projects/{id}/jobs`, `jobs/{id}`, `jobs/{id}/events`, `targets`, `profiles`.
- Backend Python is not modified. Config/task-guide PUT endpoints stay but go
  unreferenced.

---

### Phase 1: Scaffold, build integration, and Flowforge foundation

**Task Guide Input:** Create a new React 19 + Vite + TypeScript frontend under
`web/` that builds into `src/openmcp/dashboard_static/` and is served by the
existing FastMCP `/dashboard` route with zero backend changes. Vendor the
Flowforge design tokens, Libre Franklin fonts, and Lucide icons for offline use.
Build the Flowforge product-shell chrome (200px sidebar, 64px top bar) with a
light/dark theme toggle. Distinct cases: dev server with API proxy; committed
production build served under the `/dashboard/assets` mount; offline asset
loading with no CDN; dark theme via `data-theme`.
**Profile:** `Resolve at execution`
**Goal:** A committed Vite build renders the Flowforge app shell at `/dashboard`.

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`,
  `web/index.html`
- Create: `web/src/main.tsx`, `web/src/App.tsx`
- Create: `web/src/styles/colors_and_type.css` (vendored from flowforge skill),
  `web/src/styles/app.module.css`
- Create: `web/src/fonts/*.woff2` (vendored Libre Franklin), `web/src/assets/icons/`
  (vendored Lucide SVGs actually used)
- Create: `web/src/components/AppShell.tsx`, `Sidebar.tsx`, `TopBar.tsx`,
  `ThemeToggle.tsx`
- Modify (build output only): `src/openmcp/dashboard_static/` (generated)

**Tasks:**
1. Init Vite React-TS project in `web/`; add deps: `react`, `react-dom`,
   `react-router-dom`, `@tanstack/react-query`; dev deps: `vite`, `typescript`,
   `vitest`, `@testing-library/react`, `jsdom`.
2. `vite.config.ts`: `base: '/dashboard/assets/'`,
   `build.outDir: '../src/openmcp/dashboard_static'`, `build.emptyOutDir: true`,
   dev `server.proxy` routing `/dashboard/api` to `http://127.0.0.1:8765`.
3. Vendor `colors_and_type.css`, Libre Franklin woff2, and the Lucide SVGs used;
   import tokens globally; no CDN references anywhere.
4. Build `AppShell` (sidebar + top bar per Flowforge geometry) and a
   `data-theme="dark"` toggle persisted to `localStorage`.

**Acceptance Criteria:**
- `npm --prefix web run build` emits `index.html` + `assets/` into
  `src/openmcp/dashboard_static/` and removes prior Alpine files.
- Running the daemon and opening `/dashboard` renders the Flowforge shell (sidebar
  + top bar) with working light/dark toggle.
- No network/CDN requests for fonts or icons (offline).

**Reviewer Checklist:**
- Asset URLs resolve through `/dashboard/assets/` → `dashboard_static/` (no 404s).
- `emptyOutDir` does not delete anything outside the build output.
- Tokens match flowforge values; no hard-coded off-palette colors.

**Verification Checks:**
- `npm --prefix web install`
- `npm --prefix web run build`
- `ls src/openmcp/dashboard_static/index.html src/openmcp/dashboard_static/assets`

**Commit:** `feat(dashboard): scaffold react+vite flowforge app shell`

---

### Phase 2: Typed data layer and polling

**Task Guide Input:** Implement a typed API client and TanStack Query polling
layer over the existing read-only dashboard GET endpoints, including
pause-on-hidden, refetch-on-focus, and a connection/disconnection state surfaced
in the top bar. Distinct cases: periodic background polling; tab-visibility
pause/resume; transient fetch failure keeping last-known data; per-resource cache
keys.
**Profile:** `Resolve at execution`
**Goal:** Live data flows into the shell with resilient polling.

**Files:**
- Create: `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/queries.ts`
- Modify: `web/src/App.tsx` (QueryClientProvider), `web/src/components/TopBar.tsx`

**Tasks:**
1. `types.ts`: TypeScript types for Status, Project, Job, JobEvent, Target,
   Profile responses.
2. `api.ts`: typed fetch wrappers for each GET endpoint with error propagation.
3. `queries.ts`: query hooks with `refetchInterval` (~3s general, ~2s open job),
   `refetchOnWindowFocus`, and pause when `document.hidden`.
4. Wire top-bar status pill (running/degraded/disconnected) + worker/active/queued
   counts + last-updated.

**Acceptance Criteria:**
- Views receive polled data; polling pauses on tab-hidden and resumes on focus.
- A failed poll flips the pill to "disconnected" while last-known data stays
  visible (not blanked).

**Reviewer Checklist:**
- No unbounded refetch loops; intervals cleared on unmount.
- Query keys unique per resource; job aggregation handled in one place.

**Verification Checks:**
- `npm --prefix web run build`
- `npm --prefix web test -- --run`

**Commit:** `feat(dashboard): add typed api client and tanstack polling layer`

---

### Phase 3: Monitor views (Overview, Projects, Targets, Profiles)

**Task Guide Input:** Build the four monitor views and the shared Flowforge table,
status-badge, and empty-state components. Overview is an aggregating landing
(status tiles + condensed recent-jobs, target-health, projects, profiles panels).
Projects and Targets are dense tables; Profiles lists default + available.
Distinct cases: dense table rendering (44px header/56px row); status shown as
color+icon+label; empty states with declarative copy; target circuit-breaker
warning state.
**Profile:** `Resolve at execution`
**Goal:** Four read-only monitor views render live in Flowforge style.

**Files:**
- Create: `web/src/components/DataTable.tsx`, `StatusBadge.tsx`, `EmptyState.tsx`,
  `Panel.tsx`
- Create: `web/src/views/Overview.tsx`, `Projects.tsx`, `Targets.tsx`,
  `Profiles.tsx`
- Modify: `web/src/App.tsx` (routes), `web/src/components/Sidebar.tsx` (nav)

**Tasks:**
1. Shared `DataTable`, `StatusBadge` (color + Lucide icon + label), `EmptyState`,
   `Panel` per Flowforge tokens.
2. `Overview` aggregating landing with status tiles + condensed panels.
3. `Projects` and `Targets` dense tables (targets show model, capabilities,
   status, circuit-open warning).
4. `Profiles` view (default + available) and sidebar routing to all four.

**Acceptance Criteria:**
- `/`, `/projects`, `/targets`, `/profiles` render live data in Flowforge style.
- Status never conveyed by color alone; empty states use declarative sentence case.

**Reviewer Checklist:**
- Table geometry and hover/focus states match flowforge spec.
- Circuit-open / degraded target states are visually distinct and labeled.

**Verification Checks:**
- `npm --prefix web run build`
- `npm --prefix web test -- --run`

**Commit:** `feat(dashboard): add overview, projects, targets, profiles views`

---

### Phase 4: Jobs view and debug inspector

**Task Guide Input:** Build the Jobs list (cross-project aggregation, state filter,
sorted by created_at desc) and a right-docked debug Inspector that opens via
`?selected=<id>`, showing job header (id, workflow, state badge, base→result
commit) and a live event timeline polling `jobs/{id}/events`. Add Vitest tests for
DataTable, StatusBadge, Inspector, and the polling hook. Distinct cases:
aggregating jobs across projects; opening/closing the inspector via URL; live
event timeline refresh; stale-request guarding when switching jobs.
**Profile:** `Resolve at execution`
**Goal:** Job monitoring plus a live debug inspector, with tests.

**Files:**
- Create: `web/src/views/Jobs.tsx`, `web/src/components/Inspector.tsx`,
  `web/src/components/EventTimeline.tsx`
- Create: `web/src/**/*.test.tsx` (DataTable, StatusBadge, Inspector, polling hook)
- Modify: `web/src/App.tsx` (jobs route + selected param)

**Tasks:**
1. `Jobs` table: aggregate per-project jobs, sort desc, state filter, Flowforge
   dense rows; row click sets `?selected=<id>`.
2. `Inspector`: right-docked slide-in (depth4, 250ms) with job header and commit
   range; closes to restore list width.
3. `EventTimeline`: live-polls `jobs/{id}/events` (~2s), stale-request guarded on
   job switch.
4. Vitest + RTL tests for DataTable, StatusBadge, Inspector, and polling hook.

**Acceptance Criteria:**
- Jobs list updates live; filter works; inspector opens/closes via URL.
- Event timeline refreshes for a running job and stops when closed.
- `npm --prefix web test -- --run` passes.

**Reviewer Checklist:**
- Switching jobs never renders a previous job's events (request race handled).
- N+1 project/job fetch is contained and documented.

**Verification Checks:**
- `npm --prefix web run build`
- `npm --prefix web test -- --run`

**Commit:** `feat(dashboard): add jobs view and live debug inspector`

---

### Phase 5: Cutover, cleanup, and end-to-end verification

**Task Guide Input:** Produce the committed production build into
`src/openmcp/dashboard_static/`, confirm the old Alpine assets are gone, confirm
no config/task-guide editor UI remains referenced, leave backend PUT routes
untouched, and verify the daemon serves the redesigned console end to end with a
real job. Distinct cases: committed build replaces prior static files; dead
backend routes flagged not deleted; end-to-end serve + live job smoke.
**Profile:** `Resolve at execution`
**Goal:** The redesigned console fully replaces the old dashboard, verified live.

**Files:**
- Modify (generated): `src/openmcp/dashboard_static/` (new build replaces old)
- Verify removed: `dashboard_static/app.js`, `styles.css`, `vendor/alpine.min.js`,
  old `index.html`

**Tasks:**
1. Run the production build; confirm `dashboard_static/` contains only the new
   build + bundled vendored assets.
2. Grep the repo to confirm no references to config/task-guide editor UI remain;
   confirm backend `dashboard.py` PUT routes are unchanged (flag as dead paths).
3. End-to-end: start daemon, open `/dashboard`, submit a job, confirm live job
   list + event timeline; verify light/dark.

**Acceptance Criteria:**
- `dashboard_static/` holds the new build only; old Alpine files absent.
- Daemon serves the redesigned console; a submitted job appears live with a
  streaming event timeline.
- `git diff --stat` shows no changes under `src/openmcp/*.py`.

**Reviewer Checklist:**
- No orphaned imports/files; backend untouched.
- Offline: no CDN requests at runtime.

**Verification Checks:**
- `npm --prefix web run build`
- `git status --porcelain src/openmcp` (expect only dashboard_static changes)
- `git diff --stat -- 'src/openmcp/*.py'` (expect empty)

**Commit:** `feat(dashboard): cut over to react console and remove alpine assets`

---

## Notes

- Profiles are unresolved by design; the coordinator resolves workflow/profile at
  execution.
- `web/` is dev source; only `src/openmcp/dashboard_static/` ships in the Python
  package (unchanged packaging).
- A formal Gate 1 consult was deferred (dirty root with unknown files); rerun at
  execution if the root is clean and the coordinator deems it warranted.
