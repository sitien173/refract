## Original User Request

Turn the confirmed worker dashboard streaming design into an implementation plan,
then execute every phase through completion.

## Phase

Harden worker dashboard streaming and verify release artifacts.

## Tasks

- task-1: Add cross-layer tests for durable reload, SSE catch-up, retries,
  truncation, persistence failures, and historical fallback.
- task-2: Add security regression fixtures proving forbidden provider content
  never reaches persisted stream rows or dashboard responses.
- task-3: Document transcript support, limits, exclusions, legacy fallback, and
  deferred subagent streaming. Reconcile design wording with implementation.
- task-4: Run all required repository verification, rebuild assets, inspect
  failures, and correct only blocking Phase 5 failures.

## Context

Phases 1 through 4 implemented durable stream storage, normalized four provider
adapters, cursor REST replay, SSE cursor invalidation, and a bounded virtualized
dashboard transcript. Keep `job.result.text` authoritative. Do not invoke live
providers. Stream contents must exclude prompts, reasoning, tool arguments,
tool results, commands, diagnostics, credentials, environment variables, and
subagent text. Generated dashboard assets must match the frontend build.

## Files

- `tests/test_smoke.py`
- `tests/test_runtime.py`
- `tests/test_execution.py`
- `tests/test_dashboard.py`
- `web/src/integration/dashboard-flow.test.jsx`
- `README.md`
- `docs/plans/worker-dashboard-streaming/DESIGN.md`
- `src/openmcp/dashboard_static/`

## Done When

- All non-live Python tests pass.
- All frontend tests pass.
- Production dashboard build succeeds.
- Python package includes rebuilt dashboard assets.
- `openmcp doctor` succeeds.
- Security fixtures expose no forbidden transcript content.
- Final results and MCP job resources retain prior behavior.
- Documentation matches verified implementation behavior.
- `uv run pytest`
- `npm --prefix web test`
- `npm --prefix web run build`
- `uv build`
- `uv run openmcp doctor`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Use RED, GREEN, and REFACTOR for behavior changes.
Do not invoke paid or live providers. Do not change MCP contracts. Rebuild
production dashboard assets after frontend source changes. Do not refactor
unrelated code.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
