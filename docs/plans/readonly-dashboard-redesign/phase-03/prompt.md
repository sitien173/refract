# Phase 3: Secondary read-only views

## Goal & Outcome
- Plan Goal: Replace the Refract dashboard with a read-only split-pane live job console built on React 19, Vite, and TDS tokens, and keep the server free of configuration editing.
- Phase Outcome: Every nav rail item (Projects, Targets and profiles, Diagnostics, Runtime) renders its real read-only view from the kept GET endpoints. The placeholder views from Phase 2 are gone.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/readonly-dashboard-redesign/phase-03/base`
- Prior State: Phases 1 and 2 are done. Read `docs/plans/readonly-dashboard-redesign/DESIGN.md` completely (Views, Polling and Streaming, Read-Only API Contract, Errors and Edge Cases, Testing) and the Phase 3 section of `docs/plans/readonly-dashboard-redesign/PLAN.md`.
- Code Context (reuse, do not rewrite):
  - `server/web/src/api.js` already exports `fetchProjects`, `fetchProject`, `fetchTargets`, `fetchProfiles`, `fetchSettings`, `fetchDiagnostics(params)`, `fetchOverview`, `isTerminalState`. Extend it only if a needed GET helper is missing.
  - `server/web/src/hooks/usePolling.js` exports `usePolling` and `useOverview`, `useProjectJobs`, `useJob`. All fetch and poll logic for the new views goes through `usePolling` (add thin hooks next to the existing ones or in a new `hooks/` file that wraps `usePolling`). Do not call `fetch` or `setInterval` directly in components.
  - `server/web/src/router.js` (`parseHash`, `useHashRoute`, `navigateTo`) and `server/web/src/App.jsx` currently render `data-testid="placeholder-view"` for secondary routes. Replace the placeholders with the real views. `#/projects/:id` is already parsed by the router; verify and extend only if needed.
  - Existing components under `server/web/src/components/` (`JobFeed`, `JobInspector`, `StatusStrip`, `NavRail`, `ConfigInvalidBanner`) show the table, tab, announcement, and inline-style patterns (semantic `var(--...)` tokens plus vendored `tds-*` classes). Match them.
  - API response shapes are defined by the Python server, not by the client. Read `server/src/refract/dashboard.py` (routes `projects`, `projects/{id}`, `targets`, `profiles`, `settings`, `diagnostics`, `overview`) and `server/src/refract/models.py` and the code that builds those payloads to learn the exact JSON. Do not guess field names. The `profiles` response is enriched with per-workflow target chains and source labels; it contains no `system_prompt` or raw `args` and the UI must not display any such field.
  - TDS: run `tds rules`, then `tds search "<term>"`, `tds component <id>`, and `tds tokens <category>` before writing UI. Semantic tokens only, light theme only, never invent `tds-*` class names. Any extra component CSS needed (for example a table or tag component) must be copied unmodified from `/home/ngosi/projects/trulioo-labs-design-system` (commit `ae80143`) into `server/web/tds/` and imported in `server/web/src/main.jsx`; list each addition in `phase-03/journal.md` under `## Plan deviations`.

## Invariants & Boundaries
- Preserve: `server/web/vite.config.js`, `server/web/src/test/setup.js`, `package.json` dependencies, Vite `base` and `outDir`, all Phase 2 behavior and tests.
- Only GET requests. No `form`, no `input` other than filter and toggle controls, no mutating button. No new endpoints, no new dependencies.
- No duplicated fetch or polling logic outside the Phase 2 hooks.
- Out of Scope: Python code; `server/src/refract/dashboard_static/` (rebuilt in Phase 4; never run `npm run build`, use `npx vite build --outDir /tmp/refract-dash-build --emptyOutDir`); docs; the Live view, transcript, and inspector except where wiring requires a minimal change.

## Files
Allowed production and test paths:
- `server/web/src/**` (new view modules and co-located `*.test.jsx` for Projects, Targets and profiles, Diagnostics, Runtime; modify `App.jsx`, `App.test.jsx`, `router.js`, `router.test.js`, `api.js`, `api.test.js`, `hooks/usePolling.js`, `hooks/usePolling.test.jsx`, `components/NavRail.jsx` only as needed)
- `server/web/tds/**` (additions only, copied unmodified)
- `server/web/src/main.jsx` (only to import added TDS CSS)

Worker-owned phase records:
- `docs/plans/readonly-dashboard-redesign/phase-03/notes.md` (append `## Task <M>` blocks)
- `docs/plans/readonly-dashboard-redesign/phase-03/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`, and record deviations)

Read-only / Forbidden: `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, any Python file, `dashboard_static/`, `vite.config.js`, `package.json`, `package-lock.json`, secrets.

## Tasks
- task-1: TDD Projects. A project table (alias, path or id as returned, job counts if provided) at `#/projects`; detail at `#/projects/:id` showing the global default profile and the project default profile and per-workflow target chains with source attribution (global versus project override), using the real response fields. Unknown project id shows an inline not-found state.
- task-2: TDD Targets and profiles at `#/targets`. Target table with backend, model, isolation, read-only flag, active over max concurrency, breaker state, cooldown, and probing. A profile routing matrix from the enriched `profiles` response (profiles by workflow, ordered target chain, source label). Poll through `usePolling` at an interval chosen consistently with DESIGN.md.
- task-3: TDD Diagnostics and Runtime. Diagnostics at `#/diagnostics`: filters for project, category, and job id (filter controls only); pagination with the `before` cursor: load more requests `before=<next_before>` and the control disappears and requests stop when `next_before` is null; each row expandable to show expected and observed text; each row with a `job_id` links to `#/jobs/{job_id}`. Runtime at `#/runtime`: config health (valid or invalid with `latest_error` and `last_known_good_revision`), and daemon and logging settings from `fetchSettings`, read-only. Exposing no secret values.

## Done When
- Each view renders loading, empty, error, and populated states under test.
- Diagnostics pagination requests `before=<next_before>` and stops when `next_before` is null (tested with mock fetch).
- A test asserts that rendered markup for every view has no `form`, no `input` outside filter and toggle controls, and no mutating button, and that no request other than GET is issued.
- `App.jsx` renders no `placeholder-view` for any nav route.
- CSS and inline styles use only TDS semantic tokens; no hex colors, no `--color-*`; every `tds-*` class used exists in `server/web/tds`.
- Run from `/home/ngosi/projects/refract`:
  - `cd server/web && npm test` (Phase 2 baseline: 58 tests in 10 files; all must still pass)
  - `cd server/web && npx vite build --outDir /tmp/refract-dash-build --emptyOutDir`
  - `cd server/web && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|--color-' src --include='*.css'`
  - `cd server/web && ! grep -rn 'placeholder-view' src --include='*.jsx' --exclude='*.test.jsx'`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/readonly-dashboard-redesign/phase-03/journal.md`, then return that block and the matching status line from `erp.md`.
