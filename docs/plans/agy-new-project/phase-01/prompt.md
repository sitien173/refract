## Original User Request
Complete B-001 by passing `--new-project` to new agy sessions so project context files load.

## Phase
Initialize new agy sessions while preserving resumed conversations.

## Tasks
- task-1: Add failing command-capture tests for new and resumed sessions.
- task-2: Add `--new-project` only when `SESSION_ID` is empty.
- task-3: Run focused and full non-live regression checks.

## Context
`src/openmcp/backends/agy.py` currently adds `--conversation` for resumed sessions but no project flag for new sessions. Antigravity documentation states `--new-project` initializes a project. Resumed conversations retain their associated project.

## Files
- `src/openmcp/backends/agy.py`
- `tests/test_smoke.py`
- `docs/plans/agy-new-project/phase-01/notes.md`
- `docs/plans/agy-new-project/phase-01/journal.md`

## Done When
- New session argv contains `--new-project` exactly once.
- Resumed session argv omits `--new-project`.
- Resumed session argv contains `--conversation <SESSION_ID>`.
- Target arguments remain before OpenMCP transport arguments.
- `--print` and the prompt remain final.
- `uv run pytest tests/test_smoke.py -k agy -q`
- `uv run pytest -q`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Use RED -> GREEN test-driven development.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
