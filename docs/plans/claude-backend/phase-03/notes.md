<!-- ccg-shared-version: 10.0.3 -->

# Phase 3 — Decision Notes

<!--
Worker Notes template. Append one `## Task <M>` block per task. Keep the file;
never overwrite earlier task blocks. Empty sub-sections = `- none`. Every task
gets a block even if all `none`.
-->

## Task 1

### Decisions made
- Added `claude` to `BackendName`, injected a typed Claude executor, and made unknown backend names return a failure dict instead of falling through to Pi.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The compatibility runner remains transport-only; Claude receives no `args`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Runner tests initially failed because `claude_executor` was not accepted and unknown backends reached Pi; after explicit Claude/unknown branches, the focused suite passed (51 passed).

## Task 2

### Decisions made
- Extended the server literal and passed the module-level `claude_execute` into the compatibility runner.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The existing `run` parameter names remain unchanged for the compatibility API.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The focused smoke/live suite passed after server injection; existing `test_tool_signature` also passed unchanged.

## Task 3

### Decisions made
- Reused the Phase 1 import and transport-only params assertions without duplicating them.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Phase 1's committed smoke coverage remains the verification source for these invariants.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Existing Claude import and params-field assertions passed as part of the focused suite (51 passed).

## Task 4

### Decisions made
- Added injected-runner dispatch coverage and a live Claude PONG test using the shared result helper.

### Spec deviations
- none

### Tradeoffs accepted
- The live test runs against the installed Claude CLI rather than being skipped; it passed successfully.

### Assumptions
- The four `tests/test_server.py` failures are the documented pre-existing timeout-contract failures.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest -m live -k claude -q` passed (1 passed).
- `uv run pytest -q` passed 170 tests with exactly the four documented pre-existing server failures.
