# Phase 1: Repair baseline, delete Langfuse and the React dashboard

## Goal & Outcome
- Plan Goal: Refract v3 per `docs/plans/refract-v3-simplification/DESIGN.md`: six MCP tools, one async transport, fresh storage, flat config, small server-rendered dashboard, no Langfuse. Delete before adding.
- Phase Outcome: the plugin contract test passes again; Langfuse tracing and the React dashboard with its JSON API are deleted without replacement; `POST /ask` still works; the full server suite passes.

## Context & Architecture
- Root: `/home/ngosi/.worktrees/refract/refract-v3-simplification` | Branch: `refract-v3-simplification` | Base: `refs/plans/refract-v3-simplification/phase-01/base`
- Prior State: plan base `232aab7c` plus plan docs. Server suite: 1201 passed, 23 skipped, 15 deselected. `plugin/tests/test-contracts.sh` fails: its embedded Python asserts `"## Reported successful output recovery" in contract` (file line 153) and checks the text of that section in the lines after it, but commit `38f97c55` removed that section from `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`.
- Code Context:
  - Langfuse lives in `server/src/refract/observability.py` (`Tracer`, `job_event`, `generation_observation`, `job_observation`). Call sites: `ask.py:12,49-50,174,206`; `execution.py:27,78,86,~327,1070,1077,~1112` and the `finally` that finishes the job observation near `execution.py:1156`; `runtime.py:19,36,75-76,94,102,187-189`. Config: `LangfuseConfig` and `_langfuse_config` in `config.py` (~93-123, 706-748, the allowed top-level key list near 825, the constructor near 893, the project overlay near 1051, and `__all__` near 1188-1195). Optional dependency `langfuse` in `server/pyproject.toml`; `server/uv.lock`.
  - Dashboard: `server/src/refract/dashboard.py` registers status, catalog, project, diagnostics, job, job-output, asset, and ask routes; `register_dashboard_routes(state)` returns them and `server.py:984` mounts them before the MCP mount. The ask route is `_register_ask_routes` (~733-790) and depends on the loopback helpers `_host_name`, `_is_loopback_host`, `_is_loopback_client`, `_forbidden`, `_loopback_route`, and on `DashboardState`. The built bundle is `server/src/refract/dashboard_static/index.html` and `dashboard_static/assets/`. The source is `server/web/`. `server/pyproject.toml` lists `src/refract/dashboard_static/**` as sdist and wheel artifacts.

## Invariants & Boundaries
- Preserve: `/ask` request validation, token check, loopback-only guard (403 for non-loopback), `ask_timeout_s` handling, and its status codes. Job execution, scheduling, storage, MCP tools and their responses, `streaming.py`, and logging behave as before apart from the removed tracing.
- Out of Scope: building any new dashboard (Phase 7); logging config changes (Phase 6); `streaming.py` `JobStreamHub` and `StreamRecorder` deletion (Phase 5; leave them even if now unused by routes); MCP tool changes and the "dashboard" wording in `server.py` error messages (Phase 4); any skill or contract text in `plugin/skills/`; version strings; `CHANGELOG.md`.
- Never touch `/home/ngosi/projects/refract`, `~/.refract`, or the running daemon. Do not restart any service.

## Files
Allowed production and test paths:
- `plugin/tests/test-contracts.sh` (modify: drop assertions for the removed "Reported successful output recovery" section only)
- `server/src/refract/observability.py` (delete)
- `server/tests/test_observability.py` (delete)
- `server/src/refract/ask.py`, `server/src/refract/execution.py`, `server/src/refract/runtime.py`, `server/src/refract/server.py` (modify: remove tracer parameters, attributes, and calls)
- `server/src/refract/config.py` (modify: remove `LangfuseConfig`, `_langfuse_config`, the `langfuse` field; a `[langfuse]` table now raises the existing config error with a message containing `langfuse` and `removed`)
- `server/src/refract/config_inspection.py` (modify, added after clarification: only allow-list the fixed `[langfuse]` removal message in `sanitize_config_error`; the message is a constant and never includes config values; remove any other Langfuse reference in this file)
- `server/pyproject.toml` (modify: remove the `langfuse` optional dependency; keep artifacts consistent with what still exists)
- `server/uv.lock` (modify: regenerate with `uv lock` from `server/`; if the registry error blocks it, leave it unchanged and report that)
- `server/web/` (delete the whole directory)
- `server/src/refract/dashboard_static/index.html`, `server/src/refract/dashboard_static/assets/` (delete)
- `server/src/refract/dashboard.py` (modify: keep only `DashboardState`, the loopback helpers, the ask route, and a `register_dashboard_routes` returning the ask route; delete everything else)
- `server/tests/test_dashboard.py`, `server/tests/test_ask.py` (modify: keep and add `/ask` and loopback coverage; delete tests of removed routes)
- `server/tests/test_dashboard_consolidation.py` (delete)
- `server/tests/test_runtime.py`, `server/tests/test_server.py`, `server/tests/test_execution.py`, `server/tests/test_config.py` (modify: delete Langfuse and removed-route tests; add the `[langfuse]` rejection test)
- `README.md`, `server/README.md` (modify: remove Langfuse and React dashboard sections only)

- `.github/workflows/server.yml`, `.github/workflows/sonarqube.yml`, `sonar-project.properties`, `server/tests/test_config_inspection.py` (modify, added at review-fix: drop references to the deleted `server/web` and `dashboard_static`; add the removal-message passthrough assertion)

Worker-owned phase records:
- `docs/plans/refract-v3-simplification/phase-01/notes.md` (append `## Task <M>` blocks)
- `docs/plans/refract-v3-simplification/phase-01/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, other `docs/plans/*` folders, `plugin/skills/`, dependencies beyond the listed `pyproject.toml` change, or secrets.

## Tasks
- task-1: Run `bash plugin/tests/test-contracts.sh` and record the failure (RED). Remove only the assertions tied to the removed section. Re-run all three plugin tests (GREEN).
- task-2: Add a failing test that a config containing `[langfuse]` raises the config error naming the removal (RED). Delete `observability.py`, its test, every tracer import, parameter, attribute, and call, `LangfuseConfig`, `_langfuse_config`, and the `langfuse` extra. Implement the rejection (GREEN). Regenerate `uv.lock` or report why not.
- task-3: Ensure tests prove a loopback `POST /ask` reaches the registry and a non-loopback client gets 403 (write them first if missing). Delete `server/web/`, the built bundle, every dashboard route except `/ask`, the asset routes, and their tests, including `test_dashboard_consolidation.py`. Remove now-unused imports. Update READMEs.

## Done When
- `server/web` does not exist; no Langfuse or observability reference remains in `server/src`, `server/tests`, or `server/pyproject.toml`.
- A test proves `[langfuse]` fails load naming the removal; tests prove `/ask` loopback success and non-loopback 403.
- Run from `/home/ngosi/.worktrees/refract/refract-v3-simplification`:
  - `bash plugin/tests/test-session-start.sh && bash plugin/tests/test-contracts.sh && bash plugin/tests/test-stats.sh` (Baseline: `test-contracts.sh` fails with `AssertionError`)
  - `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider` (Baseline: 1201 passed, 23 skipped, 15 deselected; counts drop only by deleted tests)
  - `! git grep -niE 'langfuse|observability' -- server/src server/tests server/pyproject.toml` (Baseline: matches present)
- `uv sync` is broken by PyPI 404s; use the command above, never `uv run`.

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/.worktrees/refract/refract-v3-simplification`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/refract-v3-simplification/phase-01/journal.md`, then return that block and the matching status line from `erp.md`.
