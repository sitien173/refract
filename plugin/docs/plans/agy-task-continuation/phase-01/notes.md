## Task 1
- Split `openmcp/openmcp/src/openmcp/backends/agy.py` into `_execute_once` (original execution path) plus public `execute` wrapper with bounded continuation logic.
- Added module constants `_BRAIN_PATH`, `_CONTINUE_PROMPT`, `_AGY_MAX_CONTINUATIONS`, and `_UNCHECKED_RE`, plus `_agy_has_pending_tasks(session_id, started_at)` that uses `task.md.metadata.json.updatedAt` when available and falls back to `task.md` mtime.
- Kept model override retry recursion inside `_execute_once` by changing the recursive call target from `execute(...)` to `_execute_once(...)`, avoiding continuation-loop recursion.
- Ran `python -m pytest -x -q` in `openmcp/openmcp`: `33 passed, 4 deselected`.
