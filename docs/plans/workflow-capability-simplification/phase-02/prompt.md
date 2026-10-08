## Original User Request

Remove target capabilities. Keep fixed workflow routing.

## Phase

Remove capabilities from every supported public surface.

## Tasks

- task-1: Remove capabilities from Python response models.
- task-2: Strip legacy keys during config writes.
- task-3: Remove capabilities from React types and views.
- task-4: Update fixtures, documentation, and generated assets.

## Context

Phase 1 removed capability metadata from target configuration and execution
plans. Existing TOML capability keys still load as inert legacy input. Current
Python and dashboard adapters return transitional empty lists. Phase 2 removes
those public fields. Fixed `consult`, `implement`, and `review` workflows remain
unchanged.

## Files

- `src/openmcp/models.py`
- `src/openmcp/execution.py`
- `src/openmcp/dashboard.py`
- `src/openmcp/config_writer.py`
- `tests/test_server.py`
- `tests/test_logging.py`
- `tests/test_dashboard.py`
- `web/src/lib/types.ts`
- `web/src/lib/api.test.ts`
- `web/src/views/Targets.tsx`
- `web/src/views/Targets.test.tsx`
- `web/src/views/Overview.test.tsx`
- `README.md`
- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`
- `docs/plans/workflow-capability-simplification/phase-02/notes.md`
- `docs/plans/workflow-capability-simplification/phase-02/journal.md`

## Done When

- MCP and dashboard target responses omit capabilities.
- Dashboard config responses omit capabilities.
- Config PUT removes retained target capability keys.
- Existing TOML capability keys remain loadable.
- Target health, capacity, and model presentation remain.
- Fixed workflow discovery remains unchanged.
- Generated dashboard assets match web sources.
- `uv run pytest tests/test_server.py tests/test_logging.py tests/test_dashboard.py`
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `uv run pytest`
- `uv build`
- `tgrep -w "capabilities" src/openmcp web/src tests README.md -g "*.py" -g "*.ts" -g "*.tsx" -g "*.md"`
- Static matches remain only in explicit legacy compatibility fixtures.
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Use RED then GREEN for
changed behavior. Preserve unrelated TOML keys and comments. Maintain this
phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
