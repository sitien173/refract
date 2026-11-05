# Phase 2: Read API with bounded queries

## Goal & Outcome
- Plan Goal: Replace the server-rendered Refract dashboard with a TDS-styled React SPA backed by a bounded `/dashboard/api` JSON surface. Design: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/DESIGN.md`. Plan: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/PLAN.md` (Phase 2).
- Phase Outcome: The SPA can read every page's data through `GET /dashboard/api/...` without loading result files for the list and without reading whole stream files.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/dashboard-spa-redesign/phase-02/base`
- Prior State: Phase 1 added CSRF-guarded `POST /dashboard/api/jobs/{job_id}/cancel|retry|answer` in `server/src/refract/dashboard.py`, with helpers `_api_json_response` (adds `Cache-Control: no-store`), `_api_error`, `_map_orchestration_error`, `_check_csrf`, `_api_post_preamble`, and `_register_action_routes`. Tests live in `server/tests/test_dashboard_api.py`. Full suite: 789 passed, 15 deselected.
- Code Context:
  - `server/src/refract/database.py`: `jobs` table columns (see `CREATE TABLE jobs`); `Database.job`, `jobs(project_id)`, `job_record`, `job_view` (reads the result file via `result_path(...).read_text`), `projects()`, `stream_path(job_id)`, `result_path(job_id)`, `_TOKEN_COLUMNS`.
  - `server/src/refract/dashboard.py`: `_events(database, job_id, after)` (current output reader; it calls `readlines()` on the whole file; keep it working for the HTML route until Phase 5), `_job_list`, `_job_detail`, `_job_output`, `_targets` (HTML; reference only), `_OUTPUT_PAGE = 500`, `_loopback_route`.
  - `server/src/refract/ask.py`: `AskRegistry.get_pending(job_id)` returns `PendingQuestion(question_id, text, future, deadline)` or None. Runtime exposes `runtime.ask_registry`.
  - `server/src/refract/runtime.py`: `Runtime.targets()` returns `TargetView` list (`server/src/refract/models.py:100`); `Runtime.config_health` is a property returning `ConfigHealth` (`models.py:31`).
  - `server/src/refract/server.py:397` shows the existing `pending_question` serialization `{question_id, text}`.

## JSON Contract (implement exactly)
All responses: `Cache-Control: no-store`, errors via `_api_error` (`{error, code, unchanged, recovery}`), 404 `unknown_job`, 400 `invalid_request`, 503 `runtime_unavailable`.
- `GET /dashboard/api/jobs?state&project&workflow&target&q&cursor&limit`
  - `state`, `project` (project id), `workflow`, `target`: exact match; `q`: case-insensitive substring of job id, with LIKE wildcards escaped; `limit`: default 100, max 200, invalid -> 400; `cursor`: opaque string from a prior `next_cursor`, invalid -> 400.
  - Order `created_at DESC, id DESC`. Filters apply in SQL before keyset pagination.
  - Response `{"jobs": [JobSummary], "next_cursor": str | null, "options": {"states": [str], "projects": [{"id", "root"}], "workflows": [str], "targets": [str]}}`. Options are distinct values across all jobs, unfiltered, sorted.
  - `JobSummary` keys exactly: `id, state, project_id, project_root, workflow, profile, target, session, retry_of, failure_kind, created_at, updated_at`.
- `GET /dashboard/api/jobs/{job_id}`
  - Keys exactly: all `JobSummary` keys plus `started_at, finished_at, prompt, result, pending_question`.
  - `result`: `{text, error, failure_kind, model, duration_ms, tokens}`; `tokens` uses the `_TOKEN_COLUMNS` keys.
  - `pending_question`: `{"question_id", "text"}` from `runtime.ask_registry.get_pending(job_id)`, or null.
  - Never contains `token`, `future`, `deadline`, `execution_plan`, `execution_plan_json`, or `pgid` at any depth.
- `GET /dashboard/api/jobs/{job_id}/output?after=N`
  - `after` default 0, non-negative integer else 400.
  - Response `{"events": [...], "next": int, "has_more": bool, "available": bool, "state": str, "terminal": bool}`. Each event is the parsed JSON line plus `seq` (1-based line number); an invalid JSON line becomes `{"kind": "invalid", "data": {}, "seq": N}`. Same `seq` semantics as the existing `_events`.
  - At most 500 events per page. `has_more` is true when a further complete line exists after the page. A partial final line (no trailing newline) is withheld and does not count toward `has_more`. `next` is the last returned `seq`, or `after` when none.
  - Missing stream file: `events: []`, `available: false`, `has_more: false`.
  - The reader streams lines with a file iterator and stops after the page plus one lookahead line; it never calls `read()`/`readlines()` on the whole file.
- `GET /dashboard/api/targets`
  - `{"targets": [TargetView.model_dump()], "config": ConfigHealth.model_dump()}`.
- Any other `/dashboard/api/*` path or method-less match returns JSON 404 `{error, code: "not_found", ...}`, loopback-guarded. Register it after all specific API routes.

## Invariants & Boundaries
- Preserve: no database schema change; line-number `seq` cursor; existing HTML routes and `GET /dashboard/jobs/{job_id}/output` keep working; `database.jobs()` and `job_view` callers outside the dashboard unchanged; Phase 1 action routes and CSRF behavior unchanged; `/ask` and MCP tools unchanged.
- Out of Scope: frontend (Phase 3+), removing HTML pages (Phase 5), config editing.
- Every new route is wrapped by `_loopback_route`. SQL uses bound parameters only.

## Files
Allowed production and test paths:
- `server/src/refract/database.py` (modify: add a summary list query with filters, keyset cursor, and filter options that never reads result files)
- `server/src/refract/dashboard.py` (modify: add the four GET API routes, the bounded output reader, and the API 404 fallback)
- `server/tests/test_dashboard_api.py` (modify: contract tests)
- `server/tests/test_database.py` (modify: query tests)
- `server/tests/test_dashboard.py` (modify only the route-set assertion to include the new routes)

Worker-owned phase records:
- `docs/plans/dashboard-spa-redesign/phase-02/notes.md` (append `## Task <M>` blocks)
- `docs/plans/dashboard-spa-redesign/phase-02/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, dependencies, `server/config.toml`, or any secret-bearing file.

## Tasks
- task-1: Failing tests first, then the summary SQL query in `database.py` with filters before keyset pagination and the filter options; expose `GET /dashboard/api/jobs`. Include a test proving the list path reads no result files (e.g. monkeypatch `Path.read_text` or `Database.result_path` to raise).
- task-2: Failing tests first, then `GET /dashboard/api/jobs/{job_id}` per the contract, including a test that recursively asserts forbidden keys are absent and that `pending_question` is populated when a question is pending.
- task-3: Failing tests first, then `GET /dashboard/api/jobs/{job_id}/output` with the bounded reader, `GET /dashboard/api/targets`, and the API 404 fallback. Tests: 1200 events return 500, 500, 200 with `has_more` true, true, false; partial final line withheld; missing file gives `available: false`; unknown `/dashboard/api/nope` returns JSON 404; every new route rejects non-loopback with 403.

## Done When
- All acceptance criteria in PLAN.md Phase 2 hold.
- Run from `/home/ngosi/projects/refract/server`:
  - `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider` (Baseline: 789 passed, 15 deselected)
  - `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_database.py tests/test_dashboard.py`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/dashboard-spa-redesign/phase-02/journal.md`, then return that block and the matching status line from `erp.md`.
