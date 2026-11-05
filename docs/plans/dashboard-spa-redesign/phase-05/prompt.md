# Phase 5: Cutover, documentation, and acceptance

## Goal & Outcome
- Plan Goal: Replace the server-rendered Refract dashboard with a TDS-styled React SPA backed by `/dashboard/api`. Design: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/DESIGN.md`. Plan: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/PLAN.md` (Phase 5 section is authoritative).
- Phase Outcome (this job): `/dashboard`, `/dashboard/jobs/{job_id}`, and `/dashboard/targets` serve the SPA shell; old HTML dashboard code and vendored server-side TDS CSS are gone; tests migrated; README and CHANGELOG updated. PLAN Task 3 (manual browser acceptance) is done by the Coordinator after this job, not by you.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/dashboard-spa-redesign/phase-05/base`
- Prior State: Phases 1-4 complete. `server/src/refract/dashboard.py` has `/dashboard/api/*` (JSON, CSRF-guarded POST actions, JSON 404 fallback), preview SPA routes `/dashboard/app/*` and `/dashboard/app/assets/*` (loopback-guarded, traversal/NUL safe), plus the legacy HTML pages. SPA in `server/web/` with Vite `base: "/dashboard/app/"` and in-app router in `server/web/src/router.ts` that parses paths under that base. Full pytest 806 passed; vitest 83.
- Every route must use `_loopback_route`. Register API and asset routes before the shell catch-all. A missing asset returns 404, never the shell. `/dashboard/api/*` unknown paths stay JSON 404.

## Tasks
- task-1: PLAN.md Phase 5 Task 1, test-first. Serve the shell at `/dashboard`, `/dashboard/` and `/dashboard/{path}` deep links (jobs/{job_id}, targets); assets at `/dashboard/assets/*`. Change Vite `base` to `/dashboard/` and update `server/web/src/router.ts` (and its tests, App tests, any hardcoded `/dashboard/app` in `server/web/src`) so routing works under `/dashboard/`. Remove the `/dashboard/app` preview routes. Remove `_job_list`, `_job_detail`, `_job_output`, `_targets`, `_POLL_SCRIPT`, `_stylesheet`, `_page`, `_table`, `_tag`, `GET /dashboard/jobs/{job_id}/output`, and every helper/import orphaned by the removal. Delete `server/src/refract/dashboard_static/tds/`. Replace HTML assertions in `server/tests/test_dashboard.py` with shell, deep-link, asset, and route-set tests; update `server/tests/test_dashboard_api.py` preview-path tests to the new paths.
- task-1b (logged debt): (a) Phase 1 debt: `_api_json_response`/`_api_error` overlap `_json_response`/`_error`; once HTML helpers are removed, fold into one pair if the remaining callers allow it without changing `/ask` behavior or response shapes; otherwise leave and record why. (b) Phase 3 debt: shell responses send `Cache-Control: no-cache`, hashed assets send `Cache-Control: public, max-age=31536000, immutable`; all static responses send `X-Content-Type-Options: nosniff`; tests. (c) Phase 4 debt: set a bounded worker count in the Vitest `test` config in `server/web/vite.config.ts` (e.g. `maxWorkers: 2`) so CI is not timing-flaky under load; record reasoning in notes.
- task-2: PLAN.md Phase 5 Task 2. README dashboard section describes the SPA, its routes, live polling, actions, and how to rebuild the bundle (`cd server/web && npm ci && npm run build`, `npm run check:bundle`). `CHANGELOG.md` Unreleased entry lists every added and removed route exactly (added in this plan: `GET /dashboard/api/jobs`, `GET /dashboard/api/jobs/{job_id}`, `GET /dashboard/api/jobs/{job_id}/output`, `GET /dashboard/api/targets`, `POST /dashboard/api/jobs/{job_id}/cancel`, `POST /dashboard/api/jobs/{job_id}/retry`, `POST /dashboard/api/jobs/{job_id}/answer`, `GET /dashboard/assets/*`; removed: `GET /dashboard/jobs/{job_id}/output` and the server-rendered HTML pages now served by the SPA). Verify the exact list against the final route table in `dashboard.py` and `tests/test_dashboard.py`.
- task-3: Rebuild the bundle.

## Invariants & Boundaries
- `/ask` and its tests unchanged. Six-tool MCP schema tests unchanged. Remove only code made dead by the cutover.
- TDS rules from `phase-04/prompt.md` still apply to any frontend edit (no hex, no dark, token-only styling).

## Done When
- PLAN.md Phase 5 acceptance criteria except the TDS Rule 10 acceptance record (Coordinator does that).
- Run:
  - `cd /home/ngosi/projects/refract/server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider`
  - `cd /home/ngosi/projects/refract/server/web && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle`
  - `cd /home/ngosi/projects/refract/server && rm -rf /tmp/refract-wheel && uv build --wheel -o /tmp/refract-wheel && unzip -l /tmp/refract-wheel/*.whl | grep -q 'refract/dashboard_static/app/index.html' && ! unzip -l /tmp/refract-wheel/*.whl | grep -q 'dashboard_static/tds/'`
  - `cd /home/ngosi/projects/refract && ! grep -rn '_POLL_SCRIPT\|_stylesheet\|dashboard_static/tds' server/src`
  - `cd /home/ngosi/projects/refract/server/web/src && ! grep -rn 'dashboard/app' .`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/dashboard-spa-redesign/phase-05/journal.md`, then return that block and the matching status line from `erp.md`.
