# Phase 1 — Fix gemini/codex stream-json + agy default-model behavior

- Status: ACTIVE
- Owner: Codex
- Started: 2026-05-30T09:50:00Z
- Finished:

## Route
- Reason: back-side; three coordinated file edits to openmcp backends + server env resolution.
- Done When:
  - `python -m pytest -x -q` in `openmcp/openmcp` passes
  - gemini cmd includes `--output-format stream-json`
  - codex cmd includes `--json`
  - server `_resolve_model` agy branch returns `""` with no caller-model + no reasoning
  - per-line JSON decode guarded in both backends
- Files:
  - openmcp/openmcp/src/openmcp/backends/gemini.py
  - openmcp/openmcp/src/openmcp/backends/codex.py
  - openmcp/openmcp/src/openmcp/server.py

## External Response

## Review

## Squash Commit

## Decisions

## Handoff

# EXTERNAL RESPONSE

## Summary
- Completed all three phase tasks with one commit per task.
- Gemini now runs in stream-json mode and only consumes structured JSON events.
- Codex now runs in JSON mode and prioritizes thread/session extraction from JSONL events.
- Server no longer injects OPENMCP_AGY_MODEL_DEFAULT when backend is agy with no explicit model and no reasoning.

## Task Commits
- Task 1: `ed2e53d` `phase-1.task-1: switch gemini backend to stream-json parsing`
- Task 2: `e639592` `phase-1.task-2: parse codex json stream for session and messages`
- Task 3: `e88b642` `phase-1.task-3: stop implicit agy model default injection`

## Test Runs
- After Task 1: `python -m pytest -x -q` initially failed in env setup (`pytest` missing), then after venv activation surfaced pre-existing codex import gap (`_profile_exists` missing).
- After Task 2: `python -m pytest -x -q` passed (`34 passed, 4 deselected`).
- After Task 3: `python -m pytest -x -q` passed (`34 passed, 4 deselected`).

## Notes
- Appended `## Task 1`, `## Task 2`, and `## Task 3` blocks to `docs/plans/fix-stream-json-and-agy-default/phase-01/notes.md`.
