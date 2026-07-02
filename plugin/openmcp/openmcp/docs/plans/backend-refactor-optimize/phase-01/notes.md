<!-- ccg-shared-version: 5.3.1 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run --extra dev pytest tests/test_smoke.py::test_agy_plugin_disable_failure_does_not_swallow_body_exception -q` failed before the fix with `Failed: DID NOT RAISE RuntimeError`; after the fix, `uv run --extra dev pytest tests/test_smoke.py::test_agy_plugin_disable_failure_does_not_swallow_body_exception tests/test_smoke.py::test_agy_plugin_temporarily_disabled_and_restored tests/test_smoke.py::test_agy_plugin_restored_when_execution_fails -q` passed with `3 passed`.
- Root cause (bugfix only): `_temporary_disabled_plugin` returned from its `finally` block when disable failed, suppressing exceptions raised inside the context body.

## Task 2

### Decisions made
- Added `src/openmcp/backends/_shell.py` for the shared line-streaming implementation.
- Kept backend-specific line transforms, decode error handling, executable names, and cleanup wait times as parameters.

### Spec deviations
- none

### Tradeoffs accepted
- Used existing smoke coverage for the refactor instead of adding implementation-specific tests.

### Assumptions
- The Linux non-PTY fallback and Codex stdout mode are the only duplicated paths in scope.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: not applicable; refactor covered by existing tests.
- Task check: `uv run --extra dev pytest tests/test_smoke.py -q -k 'not test_agy_reports_pty_initialization_failure_as_fatal'` passed with `27 passed, 1 deselected`.
- Root cause (bugfix only): none.

## Task 3

### Decisions made
- Extracted `_recent_conversation_files(limit)` in `agy.py`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing fallback behavior treats missing or unreadable conversation storage as no session match.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: not applicable; refactor covered by existing tests.
- Task check: `uv run --extra dev pytest tests/test_smoke.py::test_agy_recent_conversation_file_fallback tests/test_smoke.py::test_agy_recent_conversation_file_fallback_db_format tests/test_smoke.py::test_agy_pb_signature_extraction -q` passed with `3 passed`.
- Root cause (bugfix only): none.

## Task 4

### Decisions made
- Used `@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY path only")`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The PTY initialization assertion is only meaningful on Windows.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: not applicable; platform guard only.
- Task check: `uv run --extra dev pytest tests/test_smoke.py::test_agy_reports_pty_initialization_failure_as_fatal -q` passed with `1 skipped`.
- Root cause (bugfix only): none.
