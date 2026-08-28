## Original User Request
Complete backlog item B-002 by implementing the project-context-instructions plan.

## Phase
Materialize codex instructions safely through `AGENTS.override.md`.

## Tasks
- task-1: Add reusable context-file materialization, exclusion, and cleanup helpers.
- task-2: Wrap codex attempts and sweep managed leftovers during startup.
- task-3: Test composition, Git safety, linked worktrees, refusal paths, and cleanup.

## Context
A generated root `AGENTS.override.md` must contain the instruction followed by root `AGENTS.md` verbatim. Never alter tracked or foreign files. Resolve `$GIT_COMMON_DIR/info/exclude` through Git. Remove only marker-bearing managed files.

## Files
- `src/openmcp/context_files.py`
- `tests/test_context_files.py`
- `src/openmcp/execution.py`
- `src/openmcp/runtime.py`
- `tests/test_execution.py`

## Done When
- Generated codex files preserve root guidance and stay Git-invisible.
- Cleanup covers success, failure, timeout, cancellation, and driver exceptions.
- Tracked and foreign files fail without modification.
- Startup sweeping removes only managed leftovers.
- `uv run pytest tests/test_context_files.py tests/test_execution.py`
- `uv run pytest`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
