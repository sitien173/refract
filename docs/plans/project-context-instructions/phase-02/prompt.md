## Original User Request
Complete backlog item B-002 by implementing the project-context-instructions plan.

## Phase
Snapshot each stored instruction into its immutable execution plan.

## Tasks
- task-1: Add backward-compatible instruction serialization to `ExecutionPlan`.
- task-2: Snapshot the stored project and workflow instruction during submission.
- task-3: Test round-trips, legacy parsing, validation, and queued-job immutability.

## Context
The execution plan is persisted as JSON. Keep `target_execution_key` based only on target data. Never re-read instructions during execution.

## Files
- `src/openmcp/planning.py`
- `src/openmcp/runtime.py`
- `tests/test_planning.py`
- `tests/test_server.py`

## Done When
- Instructions round-trip and legacy plans default to empty.
- Non-string instructions fail parsing.
- Submitted jobs retain their submission-time instruction.
- `target_execution_key` remains unchanged.
- `uv run pytest tests/test_planning.py tests/test_server.py`
- `uv run pytest`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
