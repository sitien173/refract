# Phase 4: Committed bundle and documentation

## Goal & Outcome
- Plan Goal: Replace the Refract dashboard with a read-only split-pane live job console and keep the server free of configuration editing.
- Phase Outcome: The committed `server/src/refract/dashboard_static` equals a fresh build of `server/web`, stale assets are gone, and the docs describe a read-only dashboard.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/readonly-dashboard-redesign/phase-04/base`
- Prior State: Phases 1 to 3 are done. Read the Phase 4 section of `docs/plans/readonly-dashboard-redesign/PLAN.md` and the Read-Only API Contract in `docs/plans/readonly-dashboard-redesign/DESIGN.md`.
- Plan base commit is `38f97c55` (`refs/plans/readonly-dashboard-redesign/base`). Use `git diff 38f97c55 HEAD -- server/src/refract/dashboard.py` and `git show 38f97c55:server/src/refract/dashboard.py` to enumerate every route removed since the base: write endpoints, config editor routes, and removed GET routes. Use `git diff 38f97c55 HEAD -- server/pyproject.toml` (and lock files) to confirm the `tomlkit` removal. Read the current `server/src/refract/dashboard.py` for the kept routes. Do not guess route names.
- Docs to rewrite: `server/README.md` sections "Admin Configuration Dashboard" and "Dashboard Management" (find them by heading), `README.md` dashboard mentions, and `CHANGELOG.md` (match its existing format and heading style).

## Invariants & Boundaries
- Do not change application source under `server/web/src`, `server/web/vite.config.js`, `package.json`, `package-lock.json`, or any Python file. The only allowed non-doc change is the regenerated bundle. If the build is not reproducible, record it in `## CLARIFICATIONS NEEDED` and return `NEXT: BLOCKED`.
- Docs must not mention dashboard configuration editing, CSRF, or If-Match, except the CHANGELOG entry that records their removal.
- Configuration changes are described as going through `~/.refract/config.toml` and `.refract/config.toml`.

## Files
Allowed paths:
- `server/src/refract/dashboard_static/**` (full regeneration; delete old hashed assets and any `flowforge` logo)
- `server/README.md`, `README.md`, `CHANGELOG.md`

Worker-owned phase records:
- `docs/plans/readonly-dashboard-redesign/phase-04/notes.md` (append `## Task <M>` blocks)
- `docs/plans/readonly-dashboard-redesign/phase-04/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden: `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, all Python and `server/web/src` files, secrets.

## Tasks
- task-1: Run `cd server/web && npm test`, then `npm run build` (this phase may run it). Ensure `server/src/refract/dashboard_static` contains exactly the fresh build output: remove assets that the new build does not produce, including anything matching `Dmt_vjdw`, `N_5a6zmM`, or `flowforge`. Run the build a second time and confirm no change.
- task-2: Rewrite the `server/README.md` dashboard sections as read-only views: Live console (job feed, transcript, inspector), Projects, Targets and profiles, Diagnostics, Runtime, with the real kept GET routes and the polling and streaming behavior from DESIGN.md. State that configuration changes go through `~/.refract/config.toml` and `.refract/config.toml`. Update `README.md` dashboard mentions to match.
- task-3: Add a `CHANGELOG.md` entry marked breaking. List every removed route by method and path (write endpoints, editor routes, removed GET routes), the CSRF and If-Match mechanism, and the `tomlkit` dependency removal. Also note the new UI stack (React 19, Vite) and the read-only behavior.

## Done When
Run from `/home/ngosi/projects/refract`:
- `cd server/web && npm test`
- `cd server/web && h() { find ../src/refract/dashboard_static -type f | sort | xargs sha256sum | sha256sum; } && npm run build >/dev/null && a=$(h) && npm run build >/dev/null && [ "$a" = "$(h)" ]`
- `cd server/web && ! ls ../src/refract/dashboard_static/assets | grep -E 'Dmt_vjdw|N_5a6zmM|flowforge'`
- `cd server && uv run --no-sync pytest -q`
- `! grep -nEi 'csrf|if-match|edit.*dashboard|dashboard.*edit' server/README.md`
- `git diff --check`
- Every removed route in the diff against `38f97c55` appears in the CHANGELOG entry.

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable. Return only the ERP block, with no preface text.
