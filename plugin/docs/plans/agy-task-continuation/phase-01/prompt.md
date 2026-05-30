# Phase 1 — Agy task-status driven continuation

You are the Codex worker. Edit **one file**:

- `C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp/src/openmcp/backends/agy.py`

## Background (do not re-investigate)

Agy sometimes exits while a checklist it created is still "in-progress" — the assistant reply says the task is pending, but agy returns control to openmcp anyway. This makes openmcp report an in-process state as if it were done.

Agy persists checklist state at:

```
~/.gemini/antigravity-cli/brain/<SESSION_ID>/task.md
~/.gemini/antigravity-cli/brain/<SESSION_ID>/task.md.metadata.json
```

- `task.md` contains lines like:
  ```
  - `[x]` M1.1 — done item
  - `[ ]` M2.4 — pending item
  ```
- `task.md.metadata.json` contains:
  ```json
  {
    "artifactType": "ARTIFACT_TYPE_TASK",
    "summary": "...",
    "updatedAt": "2026-05-26T13:14:45.401452700Z"
  }
  ```

Trigger policy (decided): continue **only when this turn actually touched task.md and unchecked items remain**. Compare `updatedAt` against the per-turn `started_at` captured at the top of `execute()`.

## Behavior to implement

### 1. Split current `execute` into two

Rename the current `execute` body into a private `async def _execute_once(params)` that returns `BackendResult` unchanged — same model-patch context manager, same plugin-disable context, same single agy subprocess call, same session-id extraction, same `_classify_output` call, same existing "model override produced no output → retry once with no model" fallback. **Do not move that retry fallback** — it stays inside `_execute_once` exactly as today.

Public `async def execute(params)` becomes a thin wrapper:

1. Call `result = await _execute_once(params)`.
2. If `result.outcome != "OK"` or not `result.SESSION_ID` → return `result` immediately.
3. Capture `outer_started_at = time.time()` **before step 1** (passed into _execute_once via a new optional parameter, or recomputed — see implementation note below).
4. Run the task-status loop (see §2). Up to **3** continuation iterations.

### 2. Task-status loop

Constants at module scope:

```python
_BRAIN_PATH = Path.home() / ".gemini" / "antigravity-cli" / "brain"
_CONTINUE_PROMPT = "Continue your work. Complete any remaining `[ ]` task items."
_AGY_MAX_CONTINUATIONS = 3
_UNCHECKED_RE = re.compile(r"^\s*-\s*`?\[\s\]`?\s", re.MULTILINE)
```

Helper:

```python
def _agy_has_pending_tasks(session_id: str, started_at: float) -> bool:
    """True iff task.md was created/updated this turn AND still has `[ ]` items."""
    if not session_id:
        return False
    task_path = _BRAIN_PATH / session_id / "task.md"
    meta_path = _BRAIN_PATH / session_id / "task.md.metadata.json"
    if not task_path.exists():
        return False
    # Prefer metadata.updatedAt; fall back to file mtime.
    updated_at: float | None = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            iso = meta.get("updatedAt", "")
            # Trim sub-microsecond precision Python can't parse (e.g. "...451452700Z")
            # by truncating to microseconds + Z, then normalizing Z → +00:00.
            ...
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            updated_at = None
    if updated_at is None:
        try:
            updated_at = task_path.stat().st_mtime
        except OSError:
            return False
    # 2-second grace window for clock skew between file mtime and time.time().
    if updated_at < started_at - 2:
        return False
    try:
        content = task_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(_UNCHECKED_RE.search(content))
```

Loop (inside public `execute`, after the first `_execute_once` returns OK with a session_id):

```python
merged_messages = result.agent_messages
session_id = result.SESSION_ID
continuations = 0
while continuations < _AGY_MAX_CONTINUATIONS and _agy_has_pending_tasks(session_id, outer_started_at):
    continuations += 1
    log.info("agy: task.md has pending [ ] items; continuation %d/%d", continuations, _AGY_MAX_CONTINUATIONS)
    continue_started_at = time.time()
    continuation = await _execute_once(
        AgyParams(
            PROMPT=_CONTINUE_PROMPT,
            cd=Path(params.cd),
            SESSION_ID=session_id,
            model="",  # never patch settings.json on continuation
        )
    )
    if continuation.outcome != "OK":
        log.warning("agy: continuation %d returned outcome=%s; stopping loop", continuations, continuation.outcome)
        # Return the original result with whatever messages we have so far, plus the failed continuation's error appended.
        result.agent_messages = (merged_messages + "\n\n" + (continuation.agent_messages or "")).strip()
        result.error = continuation.error or result.error
        return result
    if continuation.SESSION_ID:
        session_id = continuation.SESSION_ID
    merged_messages = (merged_messages + "\n\n" + continuation.agent_messages).strip()
    # advance outer_started_at so next iteration sees fresh updatedAt
    outer_started_at = continue_started_at

if continuations and _agy_has_pending_tasks(session_id, outer_started_at):
    log.warning("agy: pending [ ] items remain after %d continuations; returning partial", continuations)

result.agent_messages = merged_messages
result.SESSION_ID = session_id
return result
```

### 3. Implementation notes

- `_execute_once` keeps its own internal `started_at` for the session-id-from-recent-conversation-file fallback — do NOT replace that. The outer `started_at` for the task-status check is a separate value captured in the public `execute` before the first `_execute_once` call.
- The existing model-fallback recursion (`return await execute(AgyParams(...))` at line ~523) becomes `return await _execute_once(AgyParams(...))` — keep it inside `_execute_once` so the model-retry path doesn't itself trigger task-status looping.
- Do not move, rename, or alter `_patch_model`, `_temporary_disabled_plugin`, `_extract_session_id*`, `_classify_output`, `run_shell_command*`, or anything else outside `execute` / `_execute_once` / the three new module-level constants and `_agy_has_pending_tasks`.
- Datetime parse for `updatedAt` must tolerate the 9-digit nanosecond fractional and trailing `Z`. Sketch: regex-trim the fractional to 6 digits then `datetime.fromisoformat(...).replace(tzinfo=timezone.utc).timestamp()`. Fall back to `task_path.stat().st_mtime` on any parse failure.
- Continuation prompts go through the same plugin-disable + (no-op) model-patch path as the initial run — that's fine since `_execute_once` already wraps them.

## Constraints

- One file edited: `openmcp/openmcp/src/openmcp/backends/agy.py`.
- Do not add dependencies. Keep imports minimal — `datetime` and `timezone` are the only new stdlib needs.
- Do not refactor adjacent code. Do not change `_classify_output` semantics. Do not touch `__all__` (already exports `execute` and `AgyParams`).
- Match existing style: dataclass with slots, module-level `log`, `Path.home()` paths, broad `try/except OSError` on filesystem reads.

## Done When

- `cd C:/syncthing/Sync/.agents/plugins/superpowers-ccg/openmcp/openmcp && python -m pytest -x -q` passes.
- `agy.py` has new module constants `_BRAIN_PATH`, `_CONTINUE_PROMPT`, `_AGY_MAX_CONTINUATIONS`, `_UNCHECKED_RE`.
- `agy.py` has `_agy_has_pending_tasks(session_id, started_at)` helper.
- `agy.py` has split `_execute_once` and wrapper `execute`.
- Continuation loop bounded at 3, only fires when `task.md` was touched this turn AND has `[ ]`, only when initial outcome is OK with session id, and uses `PROMPT = "Continue your work. Complete any remaining \`[ ]\` task items."`
- No infinite-recursion risk: model-fallback retry stays inside `_execute_once`; continuation calls `_execute_once` (not `execute`).

## Tests

If you can extend `openmcp/openmcp/tests/test_smoke.py` with one focused test that monkeypatches `_execute_once` and `_BRAIN_PATH` to exercise: (a) no task.md → no loop, (b) task.md with `[ ]` updated this turn → loops up to cap, (c) task.md exists but `updatedAt` is older than `started_at` → no loop — do so. Otherwise skip; do not invent broad fixtures.

## Commit / journal

- One commit: `phase-1.task-1: agy task-status driven continuation`.
- Append `## Task 1` block to `docs/plans/agy-task-continuation/phase-01/notes.md`.
- Append full `# EXTERNAL RESPONSE` block to `docs/plans/agy-task-continuation/phase-01/journal.md` before completion line.
