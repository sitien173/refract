# Phase 2: New UI shell and live job console

## Goal & Outcome
- Plan Goal: Replace the Refract dashboard with a read-only split-pane live job console built on React 19, Vite, and TDS tokens, and keep the server free of configuration editing.
- Phase Outcome: Opening `/dashboard/` shows the split-pane live console that streams the selected job transcript in real time. Shell, status strip, nav rail with project switcher, Live job feed, job inspector, and a live virtualized transcript exist. Secondary views (Projects, Targets, Diagnostics, Runtime) render placeholders only.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/readonly-dashboard-redesign/phase-02/base`
- Prior State: Phase 1 is done. The server exposes only the read-only dashboard API. Read `docs/plans/readonly-dashboard-redesign/DESIGN.md` completely (Layout, Views, Polling and Streaming, Read-Only API Contract, Errors and Edge Cases, Testing) and the Phase 2 section of `docs/plans/readonly-dashboard-redesign/PLAN.md`.
- Code Context:
  - Web project: `server/web` (React 19, Vite 6, Vitest 3, jsdom, `@testing-library/react`, `@tanstack/react-virtual`). `package.json` scripts: `npm test` (vitest run), `npm run build`. Keep `vite.config.js` unchanged (`base: '/dashboard/'`, `outDir: '../src/refract/dashboard_static'`, test setup `./src/test/setup.js`). Do not add npm dependencies.
  - API response shapes are defined by the Python server, not by any old UI code. Read the route handlers in `server/src/refract/dashboard.py` and the models they return in `server/src/refract/models.py` to learn the exact JSON for `overview`, `projects`, `projects/{id}/jobs`, `jobs/{id}`, `jobs/{id}/output` (`items`/cursor/`has_more`/`retained_from`/`stream_status` fields as implemented), `jobs/{id}/output/updates` (SSE), and `diagnostics`. Do not guess field names.
  - All endpoints are under `/dashboard/api/`, relative to the page origin. Only GET.
  - The old UI in `server/web/src` (Flowforge-styled, with configuration editing) is deleted in this phase. Do not read it for reuse, do not copy from it, and do not reference it. Git history is the only archive.
  - TDS: the CLI `tds` is installed. Before writing any UI run `tds rules`, then `tds search "<term>"`, `tds component <id>`, and `tds tokens <category>` for each component you use. Use only semantic tokens (`--text-default`, `--surface-neutral-01..04`, `--surface-selected`, `--border-subtle`, `--padding-*`, `--gap-*`, `--radius-*`, `--font-*`, and so on from `tds rules`). Never invent `tds-*` class names; take them from `tds component <id>` output. Light theme only. Compose the virtualized transcript row from tokens and layout CSS only.

## TDS stylesheet vendoring (plan extension, approved by Coordinator)
The TDS stylesheets are not an npm dependency and live in `/home/ngosi/projects/trulioo-labs-design-system`. The plan bans hex colors and `--color-` in `server/web/src/**/*.css`, and `tokens.css` defines the core tokens. Therefore:
- Create `server/web/tds/` (outside `src`) and copy into it, unmodified: `tokens/tokens.css`, `tokens/fonts.css`, `tokens/fonts/inter/` (Inter latin woff2 only; skip Tobias fonts and other font folders, and if `fonts.css` references Tobias files, remove only those `@font-face` blocks), and the component CSS files for components you use, for example `Components/button/button.css`, `Components/tabs/tabs.css`, `Components/spinner/spinner.css`, `Components/side-nav/side-nav.css`. Keep relative `url()` paths valid. Check that each component CSS depends on nothing else, and copy `Components/_shared` files only if a component CSS needs them.
- Import them from `server/web/src/main.jsx` with relative paths such as `../tds/tokens.css`. Your own CSS under `src/` must use only semantic tokens and `tds-*` classes.
- The CSS grep check applies to `src` only. Do not edit the files you vendor.
- Add `server/web/tds/README.md` with one line: source repo path, commit `ae80143`, and that the files are vendored unmodified.

## Invariants & Boundaries
- Preserve: `server/web/vite.config.js`, `server/web/src/test/setup.js`, `package.json` dependencies, Vite `base` and `outDir`.
- Call only the kept GET endpoints. No mutating controls: no `form`, no `input` other than filter and toggle controls, no button that sends a non-GET request.
- Out of Scope: Python code; `server/src/refract/dashboard_static/` (rebuilt in Phase 4; never run `npm run build`, because it writes there, and use `npx vite build --outDir /tmp/refract-dash-build --emptyOutDir` for your own build checks); Projects, Targets, Diagnostics, and Runtime view content (Phase 3); docs.
- Do not use the words or concepts of the old UI (no Flowforge branding, no `flowforge-logo` asset).

## Files
Allowed production and test paths:
- `server/web/src/**` (delete every file except `server/web/src/test/setup.js`; then create `main.jsx`, `App.jsx`, and further modules with co-located `*.test.jsx` / `*.test.js` for the API client, hash router, polling hooks, transcript stream, shell, status strip, nav rail, job feed, inspector, and placeholder secondary views)
- `server/web/index.html` (modify: title and root only)
- `server/web/tds/**` (create: vendored TDS CSS as described above)

Worker-owned phase records:
- `docs/plans/readonly-dashboard-redesign/phase-02/notes.md` (append `## Task <M>` blocks)
- `docs/plans/readonly-dashboard-redesign/phase-02/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, any Python file, `server/src/refract/dashboard_static/`, `server/web/vite.config.js`, `server/web/package.json`, `package-lock.json`, or secrets.

## Tasks
- task-1: TDD the API client and data hooks. Polling at 3 s for `overview`; 2 s for `projects/{id}/jobs` on the Live view; 2 s for `jobs/{id}` until the job is terminal. Pause all polling while `document.visibilityState` is `hidden` and resume on `visibilitychange`. When the API is unreachable, back off to 10 s and mark data stale while keeping the last data visible. Use fake timers in tests. Poll hooks must not leak timers on unmount.
- task-2: TDD the transcript stream. At most one `EventSource`, opened only for the selected non-terminal job on `jobs/{id}/output/updates`. On each update (and on first load) page `jobs/{id}/output?after=<cursor>` until `has_more` is false. Close the stream on job switch, view change, unmount, and once the job is terminal and drained. Reconnect after errors with exponential backoff from the last cursor. Merge contiguous `assistant.text_delta` events by `entity_id`; pair `tool.started` and `tool.completed` by `entity_id`; render lifecycle markers, `stream.truncated`, `stream.persistence_failed`, and a notice when `retained_from` indicates pruned events. When `stream_status` is unavailable, fall back to showing `result.text`. Virtualize the transcript with `@tanstack/react-virtual` so thousands of events do not re-render in full; support follow-tail with a jump-to-live control. Test with a mock `EventSource` (jsdom has none): assert the count of live instances never exceeds one across job switches and unmounts.
- task-3: TDD the shell and Live view. Hash routes `#/jobs`, `#/jobs/:id`, `#/projects`, `#/projects/:id`, `#/targets`, `#/diagnostics`, `#/runtime`; secondary routes render a placeholder. Status strip: daemon connection, active, queued, unhealthy targets, config health, with a disconnected and stale state. Persistent config-invalid banner showing `latest_error` and `last_known_good_revision` and directing the user to the TOML file. Nav rail with project switcher persisted in `localStorage` (default: first project). Job feed with ACTIVE and RECENT sections and a `more_recent` note, keyboard-navigable (arrow keys and Enter), and a "follow newest running job" toggle. Inspector header: id, workflow, profile, target, context key, timestamps, attempts, token telemetry from `result.metadata.telemetry`. Failure card when `result.metadata.failure` or `result.error` is set (kind, retryable, whether `next_target` exists, link to job diagnostics). "Job not found" inline state. Tabs Transcript, Result (`result.text`, `result.error`, `result.metadata`), Plan (`execution_plan`, attempts, job-scoped diagnostics) with ARIA tab semantics and keyboard navigation. Use landmarks (`header`, `nav`, `main`, and so on).

## Done When
- `server/web/src` contains no file from the base commit except `test/setup.js`.
- Tests cover every task behavior above and pass.
- Rendered markup contains no `form`, no `input` other than filter and toggle controls, and no button that sends a non-GET request (assert this in a test).
- CSS under `server/web/src` uses only TDS semantic tokens; no hex colors, no `--color-*`.
- Run from `/home/ngosi/projects/refract`:
  - `cd server/web && npm test` (Baseline: 22 old files, 288 tests passed; those are deleted, so the new count is yours)
  - `cd server/web && npx vite build --outDir /tmp/refract-dash-build --emptyOutDir` (must succeed; use this instead of `npm run build` so the committed `dashboard_static` stays untouched; the Coordinator runs `npm run build` itself afterwards)
  - `cd server/web && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|--color-' src --include=*.css`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/readonly-dashboard-redesign/phase-02/journal.md`, then return that block and the matching status line from `erp.md`.
