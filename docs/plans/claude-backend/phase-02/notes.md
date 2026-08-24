<!-- ccg-shared-version: 10.0.3 -->

# Phase 2 — Decision Notes

<!--
Worker Notes template. Append one `## Task <M>` block per task. Keep the file;
never overwrite earlier task blocks. Empty sub-sections = `- none`. Every task
gets a block even if all `none`.
-->

## Task 1

### Decisions made
- Added `claude` only to the two requested backend allowlists.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing target validation and plan serialization rules apply unchanged to Claude.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The new Claude config-load test initially failed with the old allowlist; after the allowlist update, the scoped verification passed (104 passed).

## Task 2

### Decisions made
- Compiled Claude policy fields in the specified order after user args; `backend_profile` remains ignored and non-isolated targets receive no extra flag.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Phase 1 owns the transport flags and prompt separator, so the driver emits only target policy arguments.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Isolated, read-only, and model/reasoning argv tests initially failed because the driver had no Claude executor; after compilation and import wiring, all passed in the scoped verification (104 passed).

## Task 3

### Decisions made
- Explicitly dispatch `pi` and `claude`; an unrecognized backend returns `TARGET_FATAL` with `error_code="invalid_args"` rather than falling through to Pi.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Valid configured targets are covered by the two allowlists; the explicit fallback protects programmatic callers.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The dispatch regression test initially observed the unknown backend reaching Pi and Claude monkeypatches were unavailable; explicit branches made the Claude-only dispatch and unknown-backend tests pass.

## Task 4

### Decisions made
- Kept the carried resume assertion in the Phase 1 Claude argv test and added driver/config regression coverage in the existing smoke/config suites.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The four known `tests/test_server.py` failures are pre-existing timeout-contract failures identified by the phase prompt.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_config.py tests/test_smoke.py tests/test_planning.py -q` passed with 104 tests.
- `uv run pytest -q` passed 167 tests with exactly the four documented pre-existing `tests/test_server.py` failures.
- Claude execution-plan snapshot round-trip verified with a dedicated `uv run python` check.
