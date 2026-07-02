# Phase 01 — Backend refactor & optimization (Linux)

Read first:
- `.agents/shared/worker-contract.md`
- `.agents/shared/erp.md`
- `.agents/shared/notes-template.md`
- `.agents/shared/journal-template.md`
- `.agents/BACKEND.md`

Scope: `src/openmcp/` (server.py, backends/agy.py, backends/codex.py,
backends/__init__.py) and `tests/`. Target platform: Linux only — do not
touch the Windows-only `run_shell_command_pty` / `winpty` code path in
`agy.py` except where Task 4 requires a `skipif`.

Baseline (already captured): `uv run --extra dev pytest -q` on this machine
gives `1 failed, 35 passed, 2 deselected` plus a `SyntaxWarning: 'return' in
a 'finally' block` from `agy.py:198`. After this phase: 0 failed, 0 new
warnings, same pass count or higher.

## Task 1 — Fix return-in-finally bug (bug fix, root-cause-first)

`src/openmcp/backends/agy.py`, `_temporary_disabled_plugin` (~line 181-202).
The `finally` block does `if not disabled: return`, which silently discards
any exception raised by the wrapped `yield` body — a real correctness bug,
also flagged by pytest's `SyntaxWarning`. Write a failing regression test
first (e.g. body raises inside the context manager while `disabled=False`;
assert the exception propagates instead of being swallowed), confirm RED,
then restructure the function to avoid `return` inside `finally` (guard with
an `if disabled:` around the re-enable logic instead) without changing its
externally observed behavior otherwise. Confirm GREEN and confirm the
`SyntaxWarning` is gone.

## Task 2 — Deduplicate subprocess line-streaming helper

`src/openmcp/backends/codex.py:run_shell_command` and
`src/openmcp/backends/agy.py:run_shell_command` are near-identical
(~40 lines): `Popen` + background reader thread + `queue.Queue` polling loop
+ timeout/terminate/kill cleanup. Extract one shared implementation (e.g.
`src/openmcp/backends/_shell.py` or a function in `backends/__init__.py`)
parameterized on the executable-resolution step (`codex` vs `agy` binary
name) and reused by both call sites. Do not touch `run_shell_command_pty`
(Windows-only). Preserve exact existing behavior (line stripping rules
differ slightly between the two today — `codex.py` uses
`line.rstrip("\r\n")`, `agy.py` uses `line.strip()`; keep each call site's
own semantics via a parameter, don't silently unify them). Existing tests
covering both backends must keep passing unchanged.

## Task 3 — Deduplicate conversation-file globbing

`src/openmcp/backends/agy.py`: `_extract_session_id_from_pb_signature` and
`_extract_session_id_from_recent_conversation_file` both glob
`_CONVERSATIONS_PATH` for `*.pb` + `*.db` and sort by mtime descending.
Extract a small shared helper (e.g. `_recent_conversation_files(limit: int)
-> list[Path]`) and use it from both, removing the duplicated glob/sort
logic. No behavior change.

## Task 4 — Fix platform-specific test on Linux

`tests/test_smoke.py::test_agy_reports_pty_initialization_failure_as_fatal`
asserts a Windows/`winpty`-specific error string but the code path it
exercises only runs when `os.name == "nt"`, so on Linux it silently takes
the non-PTY branch and fails on an unrelated `FileNotFoundError`. Guard the
test with `@pytest.mark.skipif(os.name != "nt", reason="...")` (check
existing import/marker conventions in the file first) so it only runs where
the code path it's testing is actually reachable. Do not weaken the
assertion for Windows.

## Done When

- `uv run --extra dev pytest -q` from repo root: 0 failed, 0 collection
  errors, no new warnings vs. baseline above.
- `git show` for every task commit demonstrates the stated change only.
- Task 1's regression test fails before the fix and passes after (record
  in notes.md).
