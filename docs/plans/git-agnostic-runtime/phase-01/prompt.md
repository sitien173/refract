## Original User Request
Execute the `git-agnostic-runtime` folder plan one phase at a time.

## Phase
Make project registration and job execution Git-agnostic.

## Tasks
- task-1: Register any existing directory without Git inspection.
- task-2: Execute and finish jobs without Git checks or mutation.
- task-3: Remove reset-based recovery and Git repository code.

## Context
Keep existing database columns and method signatures during this phase. Pass
empty Git placeholders where required. Per-project FIFO scheduling remains
unchanged.

## Files
- `src/openmcp/runtime.py`
- `src/openmcp/execution.py`
- `src/openmcp/server.py`
- `src/openmcp/repositories.py`
- `tests/test_repositories.py`

## Done When
- Plain non-Git directories register successfully.
- Dirty worktrees do not block successful jobs.
- Restart interruption performs no reset.
- No Git subprocess remains under `src/openmcp`.
- `python -m pytest tests/test_execution.py tests/test_server.py tests/test_smoke.py`
- `tgrep -n "repositories|inspect_repository" src/openmcp || echo NONE`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
