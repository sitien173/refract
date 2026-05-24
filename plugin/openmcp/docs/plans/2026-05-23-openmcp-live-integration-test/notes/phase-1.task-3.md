# phase-1.task-3 decision note

## Decisions made (not in spec)
- Created the ignored local `.venv` with `uv sync --extra dev` because the specified `.venv/Scripts/python` interpreter did not exist at the start of verification.
- Used PowerShell executable syntax `.\.venv\Scripts\python.exe` for the required pytest runs.
- Added codex backend fallbacks that extract the session id from stdout or recent Codex exec session metadata when the marker is absent; this was required after the live codex test returned `OK` with `PONG` but an empty `SESSION_ID`.
- Added a focused unit test for the codex session-file fallback.
- Final default run: `10 passed, 2 deselected in 2.02s`; no `PytestUnknownMarkWarning`.
- Final live run: `2 passed, 10 deselected in 20.54s`.

## Spec deviations
- The first exact PowerShell invocation of `.venv/Scripts/python -m pytest -q` failed before pytest started because `.venv` was missing and PowerShell did not resolve that path form. Verification proceeded after creating `.venv` and using the equivalent PowerShell path to the venv interpreter.

## Tradeoffs accepted
- The codex fallback is bounded to recent session files for the same cwd and prompt hint to avoid scanning the full session history.
- The fallback depends on Codex exec continuing to persist JSONL session metadata under `CODEX_HOME` or `~/.codex`.

## Assumptions
- Codex session metadata ids are valid resume ids for the backend `SESSION_ID`.
- A recent session file with the same cwd and prompt hint belongs to the just-completed codex exec invocation.

## Follow-ups for human
- none
