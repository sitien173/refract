<!-- refract-shared-version: 2.0.0 -->

# Phase 2 Decision Notes

Append one task block per task using plugin/shared/notes-template.md. Preserve decisions, deviations, tradeoffs, assumptions, follow-ups and exact RED/GREEN evidence.

## Task 1

### Decisions made
- Added `Runtime.job_answer(job_id, answer)` and `AskRegistry.wait_question(job_id)`.
- Validated question presence using `has_pending(job_id)`.
- Mapped missing jobs to `unknown_job` tool error.
- Mapped jobs without pending question or in terminal states to `invalid_state`.
- Added `job_answer` tool to MCP server surface.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Answer payload bounded to max 8192 characters (Note: correction below - actual enforcement added in Corrective Cycle 1).

### Follow-ups for human
- none

### Test evidence
- Correction on test names: Initial tests implemented were `test_runtime_wait_and_job_wait_wake_early_with_pending_question`, `test_job_answer_errors`, and `test_connected_client_job_answer_and_wait` in `server/tests/test_server.py`.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Woke `Runtime.wait` concurrently on scheduler event and `AskRegistry.wait_question`.
- Exposed `pending_question` in `job_wait` result envelope when job is running and question is pending.
- Formatted `pending_question` dictionary with `question_id` and `text`.
- Preserved terminal paging, nonterminal timeouts, and jobs without questions.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Question text bounded by response envelope (Note: correction below - Refract raises `response_too_large` for oversized nonpageable metadata rather than truncating).

### Follow-ups for human
- none

### Test evidence
- Correction on test names: Initial test implemented was `test_job_wait_nonterminal_without_question` in `server/tests/test_server.py`.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Updated MCP server registered tool list from seven to eight tools.
- Updated `server/tests/test_server.py` tool count assertion to 8 tools.
- Updated `plugin/skills/coordinating-multi-model-work/references/tool-contract.md` to declare eight tools and `pending_question`.
- Updated `plugin/tests/test-contracts.sh` to assert eight tools, `job_answer`, and `pending_question`.
- Updated `server/README.md` to document eight tools and `job_answer`.
- Kept root `README.md` unchanged because it contains no tool count or tool list assertions.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `bash plugin/tests/test-contracts.sh` passed.
- Root cause (bugfix only): none

## Corrective Cycle 1

### Decisions made
- Enforced `MAX_ANSWER_LENGTH = 8192` in `Runtime.job_answer` and exposed `maxLength=8192` on `answer` in `job_answer` MCP tool schema in `server/src/refract/server.py`.
- Added direct `Runtime.job_answer` and MCP `job_answer` rejection for answers > 8192 characters with `invalid_request`, preserving pending question state on rejection.
- Verified exact accepted Unicode text delivery through `Runtime.job_answer` and `AskRegistry.ask`.
- Verified bounded `response_too_large` behavior in `job_wait` for oversized nonpageable metadata (`pending_question` text >= 35,000 chars).
- Retrieved completed task exceptions in `Runtime.wait` using `task.exception()` after `asyncio.wait(..., return_when=FIRST_COMPLETED)`, re-raising any scheduler or question errors.
- Cleaned up child tasks (`scheduler_task`, `question_task`) in `Runtime.wait` `finally` block when either task fails or the outer wait is cancelled.
- Preserved original internal `Runtime.wait(timeout_s=0)` indefinite scheduler/question wait while keeping public MCP `job_wait(timeout_s=0)` immediate.
- Cleaned up question waiters on timeout and cancellation in `AskRegistry.wait_question`.
- Added genuine end-to-end integration test using real ASGI `POST /ask` + MCP `job_wait` early wake + MCP `job_answer` delivery.
- Added `job_answer` input schema contract coverage in `server/tests/test_mcp_schema_contract.py`.
- Restored unrelated `Standard cycle` and `Sessions` paragraphs in `plugin/skills/coordinating-multi-model-work/references/tool-contract.md` to base, keeping total file line count at exactly 90 lines.
- Documented `invalid_state` and 8192 characters answer bound consistently in `tool-contract.md` and `server/README.md`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED command 1: `cd server && uv run pytest -q tests/test_mcp_schema_contract.py`
  - Observed error: `KeyError: 'maxLength'` in `test_job_answer_schema_contract`.
- RED command 2: `cd server && uv run pytest -q tests/test_server.py -k "bounds or oversized or asgi or cleanup or timeout_zero"`
  - Observed error 1: `Failed: DID NOT RAISE OrchestrationError` in `test_job_answer_bounds_and_unicode_acceptance`.
  - Observed error 2: `Failed: DID NOT RAISE RuntimeError` and `ERROR asyncio:base_events.py:1833 Task exception was never retrieved` in `test_runtime_wait_scheduler_exception_and_task_cleanup`.
  - Observed error 3: `AssertionError: assert not True` in `test_runtime_wait_indefinite_on_timeout_zero_until_question`.
- GREEN commands:
  - `cd server && uv run pytest -q tests/test_mcp_schema_contract.py`: 3 passed.
  - `cd server && uv run pytest -q tests/test_server.py -k "bounds or oversized or asgi or cleanup or timeout_zero"`: 9 passed, 51 deselected.
  - `cd server && uv run pytest -q tests/test_server.py`: 60 passed.
  - `cd plugin && bash tests/test-contracts.sh`: contract tests passed.
  - `bash plugin/tests/run.sh`: session-start, contract, and manifest validation passed.
- Root cause (bugfix only): none
