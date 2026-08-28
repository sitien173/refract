## Original User Request
Complete backlog item B-002 by implementing the project-context-instructions plan.

## Phase
Inject snapshotted instructions into claude and pi workers.

## Tasks
- task-1: Thread instructions through target execution and driver argv compilation.
- task-2: Append `--append-system-prompt` for claude and pi only.
- task-3: Document and test normal, isolated, empty, and unaffected backend behavior.

## Context
Apply the instruction inside each attempt. Emit the append flag after target args. Do not validate it as operator target args or log its contents.

## Files
- `src/openmcp/drivers.py`
- `src/openmcp/execution.py`
- `CLI_ARGUMENTS.md`
- `tests/test_execution.py`

## Done When
- Claude and pi receive the append flag, including isolated targets.
- Empty instructions preserve every backend's existing argv.
- Codex and agy remain unchanged.
- Retry attempts compile against each selected backend.
- `uv run pytest tests/test_execution.py`
- `uv run pytest`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
