<!-- refract-shared-version: 2.1.0 -->

# Phase 2 Decision Notes

Append one Task block per prompt task using the bundled notes template. Record decisions, deviations, tradeoffs, assumptions, follow-ups, and RED/GREEN evidence. Empty subsections use `- none`. Preserve earlier entries.

## Task 1

### Decisions made
- Added assertions for the acknowledgement response shape and the explicit recovery branches/safeguards in the plugin's executable contract test.

### Spec deviations
- none

### Tradeoffs accepted
- Assertions check required protocol phrases/branches while preserving the shell test's existing structural checks.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Before documentation edits, `bash plugin/tests/test-contracts.sh` failed at the new `assert "## Reported successful output recovery" in contract` assertion (Python `AssertionError`, line 136); the old guidance had no authoritative procedure. After documentation updates, `bash plugin/tests/test-contracts.sh` passed (`contract tests passed`).

## Task 2

### Decisions made
- Kept failed-job `result.metadata.retry.next_target` guidance separate from succeeded-output acknowledgement `retry` in MCP instructions.
- Documented response-only live eligibility, duplicate freshness, retention, and additive compatibility in the README.

### Spec deviations
- none

### Tradeoffs accepted
- Kept detailed procedural guidance in the plugin contract; MCP instructions state the compact operator-facing branch within the 2048-character MCP limit.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The focused server suite first caught MCP instructions exceeding the existing 2048-character constraint (2843 chars, then 2152); concise instructions restored the contract. `(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)` passed: 193 passed, 4 skipped.

## Task 3

### Decisions made
- Made `plugin/skills/coordinating-multi-model-work/references/tool-contract.md` the single detailed recovery procedure; review guidance links to it.
- Added executable contract assertions for pagination, eligibility/no-fallback, original correlation, side-effect reconciliation, fresh-session new-job submission, stale-token refresh, retention, no recursive reporting, and unchanged job APIs.

### Spec deviations
- none

### Tradeoffs accepted
- Kept the authoritative reference within the existing 90-line contract-test bound by consolidating prose.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `bash plugin/tests/test-contracts.sh` passed (`contract tests passed`). Full checks: `(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)` — 193 passed, 4 skipped; `(cd server && uv run pytest -q)` — 1255 passed, 23 skipped, 15 deselected; `git diff --check` — passed.
