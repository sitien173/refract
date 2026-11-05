# Phase 1: Trustworthy baseline and secure job actions

## Goal & Outcome
- Plan Goal: Replace the server-rendered Refract dashboard with a TDS-styled React SPA backed by a bounded `/dashboard/api` JSON surface with cancel, retry, and answer actions. Full design: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/DESIGN.md`. Full plan: `/home/ngosi/projects/refract/docs/plans/dashboard-spa-redesign/PLAN.md` (Phase 1 section).
- Phase Outcome: The full pytest suite passes reliably, and three CSRF-guarded JSON action endpoints exist: `POST /dashboard/api/jobs/{id}/cancel`, `/retry`, `/answer`, with race-safe answer delivery by question ID.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/dashboard-spa-redesign/phase-01/base`
- Prior State: No phase has run. Baseline full suite: 1 failed, 781 passed, 15 deselected. The failure is `tests/test_transport.py::test_timeout_kills_the_whole_process_group` under full-suite load (log: `python subprocess ended class=timeout after 0.64s`); it passes in isolation.
- Code Context:
  - `server/src/refract/dashboard.py`: `_loopback_route` (line ~90) guards routes; `_error(message, status_code, *, code, unchanged, recovery)` is the JSON error shape; `_runtime(state)` raises `RuntimeError` when inactive and `_runtime_error()` returns 503; `_register_ask_routes` shows JSON body parsing; `register_dashboard_routes` returns all routes.
  - `server/src/refract/ask.py:199` `AskRegistry.deliver_answer(job_id, answer)`; `PendingQuestion` has `question_id`, `text`, `future`, `deadline`; the registry uses `self._lock`.
  - `server/src/refract/runtime.py:423` `Runtime.job_answer`, `:459` `Runtime.cancel` (may return state `running`), `:503` `Runtime.retry(job_id, target="")` returns `SubmissionResult(job_id, state)`. Errors raise `OrchestrationError` with `code` (`unknown_job`, `invalid_state`, `invalid_request`, `targets_unavailable`, ...).
  - MCP tools in `server/src/refract/` call `Runtime.job_answer` without a question ID.

## Invariants & Boundaries
- Preserve: `_loopback_route` behavior for existing routes; `/ask` and its tests; MCP `answer`, `cancel`, `retry` tool schemas and behavior; `tests/test_mcp_schema_contract.py` passes unchanged; HTML page renderers untouched.
- Out of Scope: read API (Phase 2), frontend (Phase 3+), config editing, database schema change, CORS headers.
- The transport fix changes test code or fake fixtures only. If the root cause proves to be in `server/src/refract/backends/_process.py`, do not change it; return `NEXT: BLOCKED` with evidence.

## Files
Allowed production and test paths:
- `server/tests/test_transport.py` (modify: deterministic grandchild PID wait)
- `server/tests/fixtures/fake_cli/spawn_and_sleep.py` (modify only if the root cause is there)
- `server/src/refract/dashboard.py` (modify: CSRF guard and three POST action routes)
- `server/src/refract/ask.py` (modify: optional `expected_question_id` on `deliver_answer`)
- `server/src/refract/runtime.py` (modify: optional `expected_question_id` on `job_answer`)
- `server/tests/test_ask.py` (modify: question-ID matching tests)
- `server/tests/test_dashboard_api.py` (create: action and CSRF tests)

Worker-owned phase records:
- `docs/plans/dashboard-spa-redesign/phase-01/notes.md` (append `## Task <M>` blocks)
- `docs/plans/dashboard-spa-redesign/phase-01/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, dependencies, `server/config.toml`, or any secret-bearing file.

## Tasks
- task-1: Find the root cause of the `test_timeout_kills_the_whole_process_group` failure under load (systematic debugging: reproduce under CPU load, e.g. running it in parallel with a busy loop or the full suite). Make the test wait for the grandchild PID deterministically, not by a fixed timing guess. Do not just raise timeouts or skip.
- task-2: Write failing tests, then add optional keyword `expected_question_id: str | None = None` to `AskRegistry.deliver_answer` and `Runtime.job_answer`. The match check happens under the registry lock. A mismatch returns False from the registry and raises `OrchestrationError(code="invalid_state")` from the runtime, leaving the pending question in place. Omitting the argument keeps current behavior.
- task-3: Write failing tests, then add a CSRF guard and the POST routes `/dashboard/api/jobs/{id}/cancel`, `/retry` (body `{}`), `/answer` (body `{answer, question_id}`), each wrapped by `_loopback_route`. CSRF: reject with 403 unless `Origin` is present, not `null`, a loopback origin whose scheme, host, and port exactly match the request; `Sec-Fetch-Site` is `same-origin` when present; `X-Refract-Dashboard` header present with a fixed value (define a module constant, e.g. `"1"`); content type parses as `application/json` (else 400 or 415). Map errors with the `_error` shape: 400 bad input/`invalid_request`, 403 CSRF, 404 `unknown_job`, 409 `invalid_state`, 503 runtime unavailable; `targets_unavailable` may map to 503 with its retry info. Success responses: cancel `{job_id, state, success}`, retry `{job_id, state, retry_of}`, answer `{job_id, state, success}`. Every response from these routes sets `Cache-Control: no-store`. No CORS headers. Never serialize ask tokens, futures, deadlines, or execution plans.

## Done When
- Full suite passes; transport test file passes 20 consecutive runs.
- POST rejected with 403 for missing, `null`, foreign, or port-mismatched `Origin`; missing `X-Refract-Dashboard`; `Sec-Fetch-Site: cross-site`. Non-JSON content type returns 400 or 415.
- Valid cancel of a queued job returns success with state `cancelled`; cancelling a running job may return `running`.
- Retry returns a new job ID different from the source.
- Answer with a stale `question_id` returns 409 and leaves the pending question in place. MCP `answer` without a question ID still delivers.
- Run from `/home/ngosi/projects/refract/server`:
  - `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider` (Baseline: 1 failed, 781 passed, 15 deselected)
  - `for i in $(seq 20); do PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_transport.py || exit 1; done`
  - `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_ask.py tests/test_dashboard.py tests/test_mcp_schema_contract.py`

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/dashboard-spa-redesign/phase-01/journal.md`, then return that block and the matching status line from `erp.md`.
