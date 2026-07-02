# Phase 01 — Remove plugin-disable, remove winpty, simplify session-id retrieval

Read first:
- `.agents/shared/worker-contract.md`
- `.agents/shared/erp.md`
- `.agents/shared/notes-template.md`
- `.agents/shared/journal-template.md`
- `.agents/BACKEND.md`

Scope: `src/openmcp/backends/agy.py`, `tests/test_smoke.py`, `pyproject.toml`,
`AGENTS.md`. Only `agy.py` has plugin-disable/winpty logic — confirmed
`codex.py` has none, do not touch it for tasks 1-2.

User has explicitly accepted the tradeoff of removing the recursion-avoidance
guardrail in task 1 (confirmed: this can allow recursive MCP calls if agy
runs with the `superpowers-ccg` plugin enabled). Do not add it back or work
around it.

## Task 1 — Remove plugin self-disabling behavior

In `src/openmcp/backends/agy.py`:
- Delete `_run_plugin_command` and `_temporary_disabled_plugin`.
- In `_execute_once`, remove `_temporary_disabled_plugin("superpowers-ccg")`
  from the `with` statement (line ~500); keep `_patch_model(params.model)`.
- Delete now-dead tests in `tests/test_smoke.py` that exercise this behavior:
  `test_agy_plugin_temporarily_disabled_and_restored`,
  `test_agy_plugin_restored_when_execution_fails`,
  `test_agy_plugin_disable_failure_does_not_swallow_body_exception` (search
  for `_temporary_disabled_plugin` / `_run_plugin_command` / `superpowers-ccg`
  to find them all).
- Update `AGENTS.md` guardrail #4 ("Plugin self-disabling") to remove the
  stale claim; either delete the bullet or replace it with a short note that
  agy now runs without disabling any plugin (coordinator's call — keep it
  factual and brief, don't invent new guardrail language).

## Task 2 — Remove winpty / Windows ConPTY support

In `src/openmcp/backends/agy.py`:
- Delete `run_shell_command_pty` entirely (the `import winpty` function).
- Delete `_strip_ansi` and `_ANSI_ESCAPE` — confirm they have no other
  callers first (they exist solely to clean PTY output); if truly unused
  after this task, remove them, otherwise keep and note why in notes.md.
- In `_execute_once`, remove the `if os.name == "nt": ... else: ...` branch
  and always take the non-PTY, `--log-file`-based path (the current `else`
  body), unindented.
- Remove the `pywinpty>=2.0,<3.0.4; sys_platform == 'win32'` line from
  `pyproject.toml` dependencies.
- Delete now-dead tests: `test_agy_reports_pty_initialization_failure_as_fatal`,
  `test_agy_strips_windows_terminal_title_escape`,
  `test_windows_pywinpty_version_excludes_broken_release` (search test file
  for `winpty`/`_strip_ansi`/`pywinpty` to find them all).

## Task 3 — Simplify session-id retrieval to match the agymcp reference

Reference implementation (fetched from
`https://raw.githubusercontent.com/leologoli/agymcp/refs/heads/main/src/agymcp/server.py`):
it runs agy with `--log-file <path>`, then extracts the session/conversation
id by scanning the log file content with:

```python
_CONV_RE = re.compile(
    r"(?:Created|Streaming) conversation "
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
```

Apply the same idea to `src/openmcp/backends/agy.py`, adapted to this
codebase's conventions (keep the existing `_UUID_PATTERN` constant and
existing `BackendResult`/logging patterns — don't copy the reference file's
structure wholesale, just its extraction strategy):

- Add a single regex (using `_UUID_PATTERN`) matching
  `(?:Created|Streaming) conversation <uuid>`.
- Replace the entire current fallback chain in `_execute_once` (currently:
  `_extract_session_id(agent_messages) or _extract_session_id_from_history(...)
  or _extract_session_id_from_pb_signature(...) or
  _extract_session_id_from_recent_conversation_file(...) or
  _extract_session_id_from_latest_log(...) or params.SESSION_ID`) with: search
  `agent_messages` (the log file content, already read into that variable)
  for the new regex, falling back to `params.SESSION_ID` if no match — i.e.
  `new_regex.search(agent_messages) or params.SESSION_ID`. Keep the existing
  `params.SESSION_ID` fallback (needed for session-resume chaining, which
  the reference implementation doesn't have but this codebase does — this is
  an intentional superset, not a deviation to flag).
- Delete the now-unused functions: `_extract_session_id`,
  `_extract_session_id_from_history`, `_extract_session_id_from_pb_signature`,
  `_extract_session_id_from_recent_conversation_file`,
  `_extract_session_id_from_latest_log`, `_recent_conversation_files`.
- Delete now-unused module-level constants left orphaned by the above:
  `_CONVERSATIONS_PATH`, `_SESSION_ID_PATTERNS`. Keep `_UUID_PATTERN` (reused
  by the new regex) and keep `_BRAIN_PATH` / `_agy_has_pending_tasks` (an
  unrelated feature that also happens to take a session_id — do not touch).
- Delete/rewrite now-dead or now-incorrect tests exercising removed functions:
  `test_agy_extract_session_id_patterns`,
  `test_agy_recent_conversation_file_fallback`,
  `test_agy_recent_conversation_file_fallback_db_format`,
  `test_agy_pb_signature_extraction`, `test_agy_history_lookup_*` (search
  test file for each removed function name to find every reference,
  including monkeypatch.setattr calls in unrelated tests that patch these
  now-deleted attributes — those monkeypatches must be removed too, not just
  the assertions).
- Add/adjust at least one test asserting the new regex correctly extracts a
  session id from log content containing a `Created conversation <uuid>` or
  `Streaming conversation <uuid>` line, and that it falls back to
  `params.SESSION_ID` when absent.

## Done When

- `uv run --extra dev pytest -q` from repo root: 0 failed, 0 collection
  errors, no new warnings.
- `tgrep -i "winpty|pywinpty" src tests pyproject.toml` returns no matches.
- `tgrep "_temporary_disabled_plugin|_run_plugin_command|superpowers-ccg" src/openmcp/backends/agy.py` returns no matches.
- `tgrep "_extract_session_id_from_history|_extract_session_id_from_pb_signature|_extract_session_id_from_recent_conversation_file|_extract_session_id_from_latest_log|_recent_conversation_files" src tests` returns no matches.
- `git show` for every task commit demonstrates the stated change only.
