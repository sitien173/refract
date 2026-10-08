## Original User Request
Complete backlog item B-002 by implementing the project-context-instructions plan.

## Phase
Store and expose durable project context instructions.

## Tasks
- task-1: Add schema version 7 and context instruction database operations.
- task-2: Add runtime validation, MCP tool, resource, and result model.
- task-3: Add migration, persistence, validation, clearing, and cascade tests.

## Context
Follow existing project-profile resource patterns. Validate project before workflow. This phase must not change job execution or drivers.

## Files
- `src/openmcp/database.py`
- `src/openmcp/models.py`
- `src/openmcp/runtime.py`
- `src/openmcp/server.py`
- `tests/test_database.py`
- `tests/test_server.py`

## Done When
- Fresh databases use schema version 7.
- Version 6 migration preserves existing records.
- Setting, replacing, clearing, reading, validation, and cascade deletion work.
- `uv run pytest tests/test_database.py tests/test_server.py`
- `uv run pytest`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
