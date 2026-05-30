# Phase 1 — Agy task-status driven continuation

- Status: ACTIVE
- Owner: Codex
- Started: 2026-05-30T10:35:00Z
- Finished:

## Route
- Reason: back-side; single-file behavior change to agy.py to detect in-progress checklist state and loop with bounded continuation.
- Done When:
  - `python -m pytest -x -q` in `openmcp/openmcp` passes
  - `_execute_once` / `execute` split in place
  - `_agy_has_pending_tasks` + module constants present
  - continuation loop bounded at 3, only fires when this turn touched task.md and `[ ]` remain
- Files:
  - openmcp/openmcp/src/openmcp/backends/agy.py

## External Response

## Review

## Squash Commit

## Decisions

## Handoff

# EXTERNAL RESPONSE

## Summary
- Implemented task-status driven continuation in `agy.py` with a bounded loop that only continues when current-turn `task.md` updates exist and unchecked `[ ]` items remain.
- Preserved original single-run behavior inside `_execute_once`, including plugin/model contexts, session extraction fallbacks, classification semantics, and model-override retry behavior.

## Changes
- Added `_BRAIN_PATH`, `_CONTINUE_PROMPT`, `_AGY_MAX_CONTINUATIONS`, `_UNCHECKED_RE`.
- Added `_agy_has_pending_tasks(session_id, started_at)` with:
  - `task.md.metadata.json.updatedAt` parsing (nanosecond fraction + trailing `Z` tolerant).
  - Fallback to `task.md` mtime.
  - 2-second skew grace check against `started_at`.
  - Pending-task detection via unchecked checklist regex.
- Renamed the prior `execute` implementation to `_execute_once`.
- Added thin public `execute` wrapper:
  - captures `outer_started_at` before first run,
  - exits early unless first result is `OK` with `SESSION_ID`,
  - runs up to 3 continuation calls with prompt `Continue your work. Complete any remaining `[ ]` task items.`,
  - merges continuation messages and carries forward latest session id,
  - stops immediately on non-OK continuation and returns partial merged output.
- Updated model-fallback recursion call site to `_execute_once(...)` so continuation logic is not recursively re-entered.

## Validation
- Ran `python -m pytest -x -q` in `openmcp/openmcp`.
- Result: `33 passed, 4 deselected`.

## Notes
- Appended `## Task 1` to `docs/plans/agy-task-continuation/phase-01/notes.md`.
