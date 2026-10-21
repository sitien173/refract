# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Token material is joined with a NUL separator before SHA-256; token resolution only checks resolved plan candidates.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- none
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: token regression initially failed collection because `next_target_token` and `resolve_next_target` were absent; implemented token/resolver.

## Task 2

### Decisions made
- A valid token pins both the selection target IDs and plan candidate tuple; pre-check reuses `TargetExecutor._is_open`.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- none
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: runtime/server suite covers valid pinning and all-open pre-check; `uv run pytest -q tests/test_runtime.py tests/test_server.py` passed (65 passed).
- Coordinator clarification rewrite 1: dispatch-time circuit-open behavior now directly creates a job and invokes `TargetExecutor.execute`, preserving zero driver calls, failed state, circuit_open metadata, null duration, and unchanged breaker count despite submit pre-check.
- Coordinator clarification rewrites 2 and 3: parent drivers return `REQUEST_FATAL` with `request_error`, preserving dependency cancellation and retry non-reset assertions without opening the target breaker.

## Task 3

### Decisions made
- `retry_after_s` is emitted only for `targets_unavailable`, and validated as an integer >= 1; other codes retain the exact legacy fields.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- none
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: server schema regression verifies accepted targets-unavailable payload and rejects bool delay and delay on other codes; targeted suite passed.

## Task 4

### Decisions made
- Metadata is computed live for the terminal wait response and included in each page's serialized-size check; no database write is performed.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- none
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: terminal response assertions updated for ten-key null fallback and metadata envelope; targeted suite passed (65 passed).
- Full suite after Coordinator-authorized test rewrites: `uv run pytest -q` passed (568 passed, 3 deselected). `uv run pytest -q tests/test_execution.py` passed (121 passed).

## Task 5 — Fix cycle 1: blocking spec-evidence tests

### Decisions made
- none; implementation behavior required no production changes.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- Tests can establish live routing and non-persistence at Runtime level, while exercising actual MCP transport for tool errors and paging.
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: added direct regressions for live next_target/retryable with open/closed next candidate; stored JSON remains null.
- Added valid token execution assertion against both invoked target and persisted jobs.target_id; foreign profile and changed config revision token rejection, next_action, and no inserted jobs.
- Added retry all-open unchanged state/attempts/events assertions; MCP targets_unavailable payload with integer retry_after_s; multi-page terminal metadata, UTF-8 size, and recursive privacy assertions.
- Focused new regressions: 4 runtime tests and 2 server tests passed.
- Required targeted suite: `uv run pytest -q tests/test_runtime.py tests/test_server.py` — 71 passed.
- Full suite: `uv run pytest -q` — 574 passed, 3 deselected.

## Task 6 — Fix cycle 2: quality review findings

### Decisions made
- Candidate availability delay now uses the latest successfully loaded runtime catalog (`self._catalog`), not the startup config reference.
- Token hashing serializes the five bound fields as compact JSON before SHA-256.
### Spec deviations
- none
### Tradeoffs accepted
- none
### Assumptions
- none
### Follow-ups for human
- none
### Test evidence
- RED -> GREEN: cooldown-reload regression failed first with stale delay 7 rather than reloaded 23; passed after using the current catalog value.
- RED -> GREEN: canonical token-hash assertion failed first on the prior delimiter encoding; passed after compact JSON encoding.
- Updated server wait test doubles to implement `live_result_metadata`; corrected the two REQUEST_FATAL DriverResult fixtures with keyword fields.
- Required targeted suite: `uv run pytest -q tests/test_runtime.py tests/test_server.py` — 72 passed.
- Full suite: `uv run pytest -q` — 575 passed, 3 deselected.
