## Original User Request

Integrate Claude Code non-interactive mode as a new OpenMCP backend. Phase 4
documents it.

## Phase

Operators can configure a claude target from the documentation alone, including
the flags OpenMCP owns and the arguments that break it.

## Routing decision

Executed directly by the coordinator, not routed to an OpenMCP implement job.
`coordinating-multi-model-work` states that documentation work is not routed
through OpenMCP. No implement job and no review job were submitted for this
phase.

## Tasks

- task-1: Add a `## Claude Code (claude -p)` section to `CLI_ARGUMENTS.md`.
- task-2: Update the README feature list, architecture diagram, and
  prerequisites.
- task-3: Add a claude target and a claude-based profile to the README
  configuration example.

## Files

- `CLI_ARGUMENTS.md`
- `README.md`

## Done When

- `CLI_ARGUMENTS.md` documents the exact argv OpenMCP owns for claude.
- The unsupported arguments list names `--no-session-persistence`,
  `--fork-session`, `--bg`, `--worktree`, and `--bare`, each with its reason.
- The README architecture diagram shows a fourth adapter.
- The README configuration example loads under `uv run openmcp doctor`.
- `uv run openmcp doctor`
- `uv run pytest -q`

## Rules

Documented flags must match the installed CLI, not a guessed surface. The
`--bare` warning must state that it breaks OAuth authentication. The isolation
description must match what `--safe-mode` actually disables. No credentials in
any example `args` array. Existing sections for agy, codex, and pi stay
untouched.
