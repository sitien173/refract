# Phase 3: Frontend foundation and bundle pipeline

## Goal & Outcome
- Plan Goal: Replace the server-rendered Refract dashboard with a TDS-styled React SPA (Vite, TypeScript, Tailwind v4, shadcn/ui) backed by `/dashboard/api`. Design: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/DESIGN.md`. Plan: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/PLAN.md` (Phase 3 section is authoritative for files, tasks, acceptance, and checks).
- Phase Outcome: `/dashboard/app/*` serves a built TDS-styled SPA shell from `server/src/refract/dashboard_static/app/`, and CI fails when the committed bundle is stale.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/dashboard-spa-redesign/phase-03/base`
- Prior State: Phases 1 and 2 added `/dashboard/api` (GET jobs, jobs/{job_id}, jobs/{job_id}/output, targets; CSRF-guarded POST cancel/retry/answer; JSON 404 fallback for `/dashboard/api` and `/dashboard/api/{rest:path}`) in `server/src/refract/dashboard.py`. Full suite: 803 passed, 15 deselected.
- Code Context: `server/src/refract/dashboard.py` registers routes via `register_dashboard_routes` and guards every route with `_loopback_route`; `server/tests/test_dashboard.py` asserts the exact route set (update that assertion only). Existing TDS CSS: `server/src/refract/dashboard_static/tds/{tokens,fonts,data-table,tag,announcement}.css`. `server/web/` holds only ignored `node_modules/` and `coverage/`; check `.gitignore` so `server/web/node_modules` stays ignored and `dashboard_static/app/` is committed. Packaging: check `server/pyproject.toml` so the wheel includes `refract/dashboard_static/app/**`. CI: `.github/workflows/server.yml` (job `cross-platform`); `.github/workflows/release.yml` calls `server.yml` as `server-tests`.
- Toolchain: Node `v24.18.0`, npm `11.16.0`. TDS CLI is installed as `tds` (`tds rules`, `tds component <id>`, `tds catalog`, `tds tokens all`).
- Verify library APIs and versions with `npx ctx7@latest library <Name> "<question>"` then `npx ctx7@latest docs <id> "<question>"` (Vite, Tailwind CSS v4, shadcn/ui, Radix, Vitest, Testing Library) before writing config.

## TDS and shadcn/ui rules (mandatory)
- Behavior layer: shadcn/ui components with Radix primitives (keyboard, focus, ARIA intact). Look layer: TDS classes (`tds-*`) from `tds component <id>` and TDS semantic tokens only.
- Save TDS CSS under `server/web/src/styles/tds/`, imported with `@import "./tds/<file>.css" layer(components);`. The TDS loader strips `@import`, so fetch shared atoms (`field-label`, `field-caption`, `field-validation`, `dropdown-panel`, `caret`) explicitly when a component needs them.
- `globals.css` token bridge (TDS token definitions load before it): `--background`, `--card`, `--popover` -> `var(--surface-neutral-01)`; `--foreground`, `--card-foreground`, `--popover-foreground`, `--secondary-foreground`, `--accent-foreground` -> `var(--text-default)`; `--primary` -> `var(--interactive-default)`; `--primary-foreground` -> `var(--text-inverse)`; `--secondary`, `--muted` -> `var(--surface-neutral-02)`; `--muted-foreground` -> `var(--text-description)`; `--accent` -> `var(--surface-hover)`; `--destructive` -> `var(--border-negative)`; `--border` -> `var(--border-subtle)`; `--input` -> `var(--border-strong)`; `--ring` -> `var(--border-focus)`. Add `--font-sans: var(--font-family);` in `@theme inline`.
- Remove `.dark` and `@custom-variant dark`. Clear Tailwind's default palette and radius with `--color-*: initial;` and `--radius-*: initial;` in `@theme` to avoid collisions with TDS (`--color-neutral-100`, `--radius-md`). No circular references such as `--radius: var(--radius-card)`.
- Button mapping: `default` -> `tds-btn--primary`, `secondary`/`outline` -> `tds-btn--secondary`, `destructive` -> `tds-btn--danger`, `ghost` -> `tds-btn--invisible`; sizes `sm`/`default`/`lg` -> `tds-btn--sm`/`--md`/`--lg`; `size="icon"` -> `tds-icon-btn`. Other components (Select, Input, Tabs, Dialog, AlertDialog) use their TDS classes; Resizable has no TDS match, style its handle with TDS tokens only.
- Tailwind utilities are allowed for layout only, using TDS token values (e.g. `gap-(--gap-md) p-(--padding-xl)`). No Tailwind color, font, or radius utilities. No hardcoded hex colors anywhere in `server/web/src`.
- Light theme only. Sentence case UI text. Icon-only buttons need `aria-label`.

## Invariants & Boundaries
- Preserve: existing HTML pages at `/dashboard`, `/dashboard/jobs/{job_id}`, `/dashboard/jobs/{job_id}/output`, `/dashboard/targets`; all `/dashboard/api` behavior; `/ask`; MCP tools; `server/src/refract/dashboard_static/tds/` (removed in Phase 5, not now).
- Mount the SPA at preview path `/dashboard/app/*` (Vite `base: "/dashboard/app/"` for this phase). Assets under `/dashboard/app/assets/*`; a missing asset returns 404, never the shell. Every new route uses `_loopback_route`. Vite `build.outDir` is `server/src/refract/dashboard_static/app/` with `emptyOutDir` limited to that directory only.
- Out of Scope: console features (Phase 4), cutover (Phase 5), dark theme.

## Files
Allowed production and test paths:
- Create: `server/web/package.json`, `server/web/package-lock.json`, `server/web/.nvmrc` (`24.18.0`)
- Create: `server/web/index.html`, `server/web/vite.config.ts`, `server/web/tsconfig.json` (plus `tsconfig.*.json` if the scaffold needs them), `server/web/components.json`
- Create: `server/web/src/main.tsx`, `server/web/src/App.tsx` (minimal shell: heading "Refract dashboard" and a placeholder using Button), `server/web/src/lib/utils.ts` if shadcn needs `cn`
- Create: `server/web/src/styles/globals.css`, `server/web/src/styles/tds/*.css`
- Create: `server/web/src/components/ui/{button,select,input,tabs,dialog,alert-dialog,resizable}.tsx`
- Create: `server/web/src/test/setup.ts`, `server/web/src/styles/tokens.test.tsx`
- Create: `server/web/scripts/check-bundle.mjs`
- Create: `server/src/refract/dashboard_static/app/**` (build output)
- Modify: `server/src/refract/dashboard.py`, `server/tests/test_dashboard_api.py`, `server/tests/test_dashboard.py` (route-set assertion only)
- Modify: `.github/workflows/server.yml`
- Modify if needed: `server/pyproject.toml` (package data for `dashboard_static/app/**` only), `.gitignore` (web build ignores only)

Worker-owned phase records:
- `docs/plans/dashboard-spa-redesign/phase-03/notes.md` (append `## Task <M>` blocks)
- `docs/plans/dashboard-spa-redesign/phase-03/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, `server/config.toml`, secrets, or Python dependencies.

## Tasks
- task-1: Scaffold the app with npm scripts `dev`, `build`, `typecheck` (`tsc --noEmit`), `test` (Vitest, jsdom), `check:bundle`. Copy TDS CSS from `server/src/refract/dashboard_static/tds/` and fetch extra components with `tds component <id>` (button, icon-button, select, text-input, tabs, tab-item, dialog, announcement, spinner plus shared atoms). Write the token bridge.
- task-2: Add the shadcn components with TDS classes. Vitest checks that computed color and radius on Button, and on portalled Dialog and Select content, resolve to TDS token values (e.g. assert the computed or declared CSS variable chain resolves to `--interactive-default`, `--radius-button`, `--radius-modal`; jsdom does not lay out, so assert on resolved custom properties and applied `tds-*` classes and portal placement inside `document.body`).
- task-3: Failing pytest tests first, then serve the shell at `GET /dashboard/app` and `/dashboard/app/{path:path}` (index fallback) and hashed assets at `/dashboard/app/assets/{path}` with 404 for missing assets, path traversal blocked, all loopback-guarded. Register before existing page routes where ordering matters.
- task-4: `check-bundle.mjs` builds into a temp directory (`vite build --outDir <tmp> --emptyOutDir`) and compares every file name and byte with `dashboard_static/app/`; exits non-zero on any difference, added file, or missing file. Add a `web` job to `server.yml` on `ubuntu-latest` with `actions/setup-node` using `server/web/.nvmrc`, `npm ci`, typecheck, test, and `check:bundle`, working directory `server/web`. Make `cross-platform` (or the workflow) depend on it so `release.yml`'s `server-tests` requires it.
- Build the bundle (`npm run build`) so `dashboard_static/app/` is committed-ready.

## Done When
- PLAN.md Phase 3 acceptance criteria hold.
- Run:
  - `cd /home/ngosi/projects/refract/server/web && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle`
  - `cd /home/ngosi/projects/refract/server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py`
  - `cd /home/ngosi/projects/refract/server && rm -rf /tmp/refract-wheel && uv build --wheel -o /tmp/refract-wheel && unzip -l /tmp/refract-wheel/*.whl | grep -q 'refract/dashboard_static/app/index.html'`
  - `cd /home/ngosi/projects/refract/server/web/src && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|\.dark\b|custom-variant dark' --include='*.css' --include='*.tsx' .`
  - Demonstrate in notes: editing a source file without rebuilding makes `check:bundle` fail, and adding or deleting a file in `dashboard_static/app/` makes it fail; then restore.

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/dashboard-spa-redesign/phase-03/journal.md`, then return that block and the matching status line from `erp.md`.
