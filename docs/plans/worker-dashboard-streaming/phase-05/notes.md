<!-- ccg-shared-version: 10.5.0 -->

# Phase 5 — Decision Notes

## Task 1

### Decisions made
- Added cross-layer tests across runtime, dashboard, and execution.
- Tested database reload and cursor reconstruction.
- Tested SSE catch-up after reconnect.
- Tested target attempt boundary separation across retries.
- Tested stream truncation and final result independence.
- Tested persistence failure tolerance without job abort.
- Tested historical job fallback to authoritative result.
- Added multi-attempt and truncation rendering tests.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Database schema version 11 persists durable streams.
- Reconstructed cursor resumes at previous high-water mark.

### Follow-ups for human
- none

### Test evidence
- `tests/test_runtime.py`: passed 14 tests.
- `tests/test_dashboard.py`: passed 38 tests.
- `tests/test_execution.py`: passed 50 tests.
- `web/src/integration/dashboard-flow.test.jsx`: passed 6 tests.

## Task 2

### Decisions made
- Added security regressions for four providers.
- Proved forbidden content never enters SQLite rows.
- Proved dashboard endpoints omit prompts and reasoning.
- Proved dashboard endpoints omit tool arguments and results.
- Proved dashboard endpoints omit secrets and diagnostics.
- Proved UI DOM suppresses sensitive provider fields.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Allowlisted event normalization drops all forbidden metadata.

### Follow-ups for human
- none

### Test evidence
- `test_security_regressions_forbidden_provider_content_not_in_dashboard_or_db`: passed.
- `test_execution_security_regression_fixtures_strip_forbidden_content`: passed.
- `web/src/integration/dashboard-flow.test.jsx`: passed.

## Task 3

### Decisions made
- Added streaming section to `README.md`.
- Documented provider support and unstructured fallback behavior.
- Documented content exclusions and storage limits.
- Documented authoritative final result semantics.
- Documented historical fallback and deferred subagent streaming.
- Updated status in `DESIGN.md` to confirmed and verified.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Documentation reflects verified implementation behavior.

### Follow-ups for human
- none

### Test evidence
- Checked `README.md` and `DESIGN.md` text against implementation.

## Task 4

### Decisions made
- Added `emitter` to expected backend parameter fields.
- Preserved unstructured stdout fallback without promoting raw Agy logs.
- Selected the `_execute_once` call signature before prompt execution.
- Rebuilt production dashboard assets with Vite.
- Re-ran complete test suites and release checks.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Production dashboard bundle matches frontend source code.

### Follow-ups for human
- none

### Test evidence
- `uv run pytest`: 378 passed, 3 deselected.
- `npm --prefix web test`: 18 files passed, 144 tests passed.
- `npm --prefix web run build`: built cleanly in 2.04s.
- `uv build`: built wheel and sdist cleanly.
- `uv run openmcp doctor`: exited code 0.
- `git diff --check`: exited code 0.

## Review Fix

### Decisions made
- Kept raw `log_text` strictly for session extraction.
- Excluded raw logs from `agent_messages` and results.
- Inspected `_execute_once` signature prior to prompt execution.
- Removed broad `TypeError` catch from `_execute_sync`.
- Exercised Claude, Codex, Pi, and Agy fixtures.
- Exercised adapters in worker threads using `to_thread`.
- Injected forbidden args and results into UI fixtures.
- Verified DOM excludes all injected forbidden fields.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Adapters execute synchronously in dedicated worker threads.

### Follow-ups for human
- none

### Test evidence
- `tests/test_execution.py`: 54 passed in 5.86s.
- `tests/test_dashboard.py`: 38 passed in 1.18s.
- Combined execution and dashboard tests: 92 passed in 12.17s.
- `dashboard-flow.test.jsx`: 7 passed in 1.50s.
- Production dashboard built cleanly with Vite in 2.08s.
- `git diff --check`: passed with zero errors.
