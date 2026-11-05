# Phase 4: Console features

## Goal & Outcome
- Plan Goal: Replace the server-rendered Refract dashboard with a TDS-styled React SPA backed by `/dashboard/api`. Design: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/DESIGN.md`. Plan: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/PLAN.md` (Phase 4 section is authoritative for files, tasks, acceptance, reviewer checklist, and checks).
- Phase Outcome: the preview SPA at `/dashboard/app/*` reaches feature parity with the current HTML pages (job list, job detail, output transcript, targets) and adds every confirmed enhancement: split-pane console, URL state, live polling, filters and search, transcript reducer, cancel/retry/answer actions.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/dashboard-spa-redesign/phase-04/base`
- Prior State: Phase 3 built `server/web/` (Vite, React 19, TS strict, Tailwind v4, shadcn/ui wrappers in `src/components/ui/` with TDS classes, token bridge in `src/styles/globals.css`, TDS CSS in `src/styles/tds/`), loopback-guarded routes `/dashboard/app/*` and `/dashboard/app/assets/*` in `server/src/refract/dashboard.py`, `npm run check:bundle`, CI web job. Vite `base` is `/dashboard/app/`; the router must work under that base. Full suite: 806 passed.
- API contract: `/dashboard/api` request and response shapes are specified in `docs/plans/dashboard-spa-redesign/phase-02/prompt.md` section "JSON Contract" (and Phase 1 action routes in `phase-01/prompt.md`). Read them and the actual handlers in `server/src/refract/dashboard.py`; the code is authoritative when they differ. POST actions require header `X-Refract-Dashboard` and `Content-Type: application/json`; answer requires `question_id`.
- Event shapes for transcript fixtures: derive from the backends in `server/src/refract/backends/` (Codex, Claude, Pi, agy). Do not invent fields the backends never emit.
- Verify library APIs with `npx ctx7@latest library <Name> "<question>"` then `npx ctx7@latest docs <id> "<question>"` before using them.

## TDS and shadcn/ui rules (mandatory)
- Behavior layer: shadcn/ui components with Radix primitives (keyboard, focus, ARIA intact). Look layer: TDS classes (`tds-*`) from `tds component <id>` and TDS semantic tokens only.
- Save TDS CSS under `server/web/src/styles/tds/`, imported with `@import "./tds/<file>.css" layer(components);`. The TDS loader strips `@import`, so fetch shared atoms (`field-label`, `field-caption`, `field-validation`, `dropdown-panel`, `caret`) explicitly when a component needs them.
- `globals.css` token bridge (TDS token definitions load before it): `--background`, `--card`, `--popover` -> `var(--surface-neutral-01)`; `--foreground`, `--card-foreground`, `--popover-foreground`, `--secondary-foreground`, `--accent-foreground` -> `var(--text-default)`; `--primary` -> `var(--interactive-default)`; `--primary-foreground` -> `var(--text-inverse)`; `--secondary`, `--muted` -> `var(--surface-neutral-02)`; `--muted-foreground` -> `var(--text-description)`; `--accent` -> `var(--surface-hover)`; `--destructive` -> `var(--border-negative)`; `--border` -> `var(--border-subtle)`; `--input` -> `var(--border-strong)`; `--ring` -> `var(--border-focus)`. Add `--font-sans: var(--font-family);` in `@theme inline`.
- Remove `.dark` and `@custom-variant dark`. Clear Tailwind's default palette and radius with `--color-*: initial;` and `--radius-*: initial;` in `@theme` to avoid collisions with TDS (`--color-neutral-100`, `--radius-md`). No circular references such as `--radius: var(--radius-card)`.
- Button mapping: `default` -> `tds-btn--primary`, `secondary`/`outline` -> `tds-btn--secondary`, `destructive` -> `tds-btn--danger`, `ghost` -> `tds-btn--invisible`; sizes `sm`/`default`/`lg` -> `tds-btn--sm`/`--md`/`--lg`; `size="icon"` -> `tds-icon-btn`. Other components (Select, Input, Tabs, Dialog, AlertDialog) use their TDS classes; Resizable has no TDS match, style its handle with TDS tokens only.
- Tailwind utilities are allowed for layout only, using TDS token values (e.g. `gap-(--gap-md) p-(--padding-xl)`). No Tailwind color, font, or radius utilities. No hardcoded hex colors anywhere in `server/web/src`.
- Light theme only. Sentence case UI text. Icon-only buttons need `aria-label`.

- Phase 3 debt you own now:
  - `src/components/ui/resizable.tsx` is a non-functional stub. Replace it with the shadcn Resizable built on `react-resizable-panels` (the one allowed new runtime dependency; state the reason in notes), keyboard-resizable handle with `aria-label`, styled with TDS tokens only.
  - Restore render tests asserting Button, Dialog, Select carry their `tds-*` classes and that Dialog/Select content portals into `document.body`.
  - Extend the bridge test in `src/styles/tokens.test.tsx` to all bridge variables listed above, and assert every `var(--x)` referenced by the bridge is defined in `tokens.css`.
  - TDS spinner SVGs were unavailable in Phase 3; if a loading indicator needs them, use the TDS Spinner CSS with a documented fallback and record it in notes.

## Invariants & Boundaries
- Read only through `/dashboard/api`. Never render raw HTML from events; no `dangerouslySetInnerHTML` anywhere. Do not invent timestamps or tool output. Sentence case for all UI text. Icon-only buttons need `aria-label` (TDS Rule 9).
- Preserve: existing HTML pages, all `/dashboard/api` and `/ask` behavior, MCP tools. Do not modify Python files in this phase except if a test proves an API bug; then stop and report it under CLARIFICATIONS NEEDED instead of fixing it.
- Out of Scope: cutover from `/dashboard` to the SPA, removal of HTML pages, docs (Phase 5).

## Files
- Exactly the PLAN.md Phase 4 file list, plus: `server/web/src/components/ui/resizable.tsx`, `server/web/src/styles/tokens.test.tsx`, other files under `server/web/src/components/ui/` and `server/web/src/styles/tds/` if a new TDS component is needed, `server/web/package.json`, `server/web/package-lock.json`, `docs/plans/dashboard-spa-redesign/phase-04/{notes,journal}.md`.

## Tasks
- task-1: PLAN.md Phase 4 Task 1 (`api.ts`, `usePolling`, `useJobOutput`), test-first with fake timers: ~1 s interval, no overlap, stale discard on selection change, pause while `document.hidden`, ~5 s backoff on error, drain `has_more` after the job ends, cleanup on unmount.
- task-2: PLAN.md Phase 4 Task 2 (transcript reducer, fixtures, viewer), test-first, including the hostile string `<img src=x onerror=alert(1)>` rendered as text.
- task-3: PLAN.md Phase 4 Task 3 (split-pane console, query-string filters and search, selected job in path, targets view, actions with AlertDialog, "Cancellation requested", retry selects new job, answer dialog sends `question_id`, results as TDS announcements, buttons disabled while in flight, deep-link reload restores state), test-first. Plus the Phase 3 debt items above.
- task-4: Rebuild the bundle (`npm run build`) so `check:bundle` passes.

## Done When
- PLAN.md Phase 4 acceptance criteria and reviewer checklist hold.
- Run:
  - `cd /home/ngosi/projects/refract/server/web && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle`
  - `cd /home/ngosi/projects/refract/server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py`
  - `cd /home/ngosi/projects/refract/server/web/src && ! grep -rn 'dangerouslySetInnerHTML' .`
  - `cd /home/ngosi/projects/refract/server/web/src && ! grep -rnE '#[0-9a-fA-F]{3,8}\b|\.dark\b|custom-variant dark' --include='*.css' --include='*.tsx' --include='*.ts' . | grep -v '^./styles/tds/'`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/dashboard-spa-redesign/phase-04/journal.md`, then return that block and the matching status line from `erp.md`.
