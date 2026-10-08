## Original User Request
Execute the `git-agnostic-runtime` folder plan one phase at a time.

## Phase
Make project registration and job execution Git-agnostic.

## Tasks
- task-1: Register any existing directory without Git inspection.
- task-2: Execute and finish jobs without Git checks or mutation.
- task-3: Remove reset-based recovery and Git repository code.
- task-4: Remove Git from CLI doctor prerequisites and stale tool wording.
- task-5: Replace tests that assert Git-owned lifecycle behavior.

## Context
Keep existing database columns and method signatures during this phase. Pass
empty Git placeholders where required. Per-project FIFO scheduling remains
unchanged. Backend-specific repository rules remain outside this phase.

Consultation confirmed these details:
- Preserve the empty-alias guard and duplicate-root error handling.
- Rename recovery logging to interruption logging.
- Keep cancellation and shutdown state selection unchanged.
- Keep non-Git final logging while removing repository refresh.
- Treat `head_commit=""`, `clean=True`, `base_commit=""`, and result
  `commit=""` as temporary compatibility placeholders.
- Replace commit, reset, clean-worktree, read-only mutation, recovery, and
  detached-head expectations with Git-agnostic behavior.
- Cover missing paths, file paths, shutdown interruption, and no Git spawn.
- Remove CLI doctor's Git payload, logging field, and exit condition.

## Files
- `src/openmcp/runtime.py`
- `src/openmcp/execution.py`
- `src/openmcp/server.py`
- `src/openmcp/cli.py`
- `src/openmcp/repositories.py`
- `tests/test_repositories.py`
- `tests/test_execution.py`
- `tests/test_server.py`
- `tests/test_smoke.py`

## Done When
- Plain non-Git directories register successfully.
- Dirty worktrees do not block successful jobs.
- Restart interruption performs no reset.
- No Git subprocess remains under `src/openmcp`.
- CLI doctor does not require or report Git.
- Compatibility model fields contain empty placeholders.
- `python -m pytest tests/test_execution.py tests/test_server.py tests/test_smoke.py`
- `tgrep -n "repositories|inspect_repository" src/openmcp || echo NONE`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
