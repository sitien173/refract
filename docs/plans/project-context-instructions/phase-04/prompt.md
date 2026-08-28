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

## Consultation Constraints
- Compose from the target file's sibling `AGENTS.md`, using bytes.
- Detect tracked paths through Git index membership, even when deleted.
- Refuse symlinks, hardlink hazards, directories, and foreign files. Create exclusively.
- Scrub repository-affecting `GIT_*` variables from internal Git calls.
- Treat only confirmed non-repositories as non-Git. Fail closed otherwise.
- Verify exclusion with `git check-ignore`; anchor patterns to repository paths.
- Serialize shared exclude updates and preserve unrelated content.
- Cleanup synchronously. Delete only regular marker-bearing files.
- Sweep only marker-bearing untracked files. Skip Git when no candidate exists.
- Keep materialization per attempt and cleanup unable to mask outcomes.

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
