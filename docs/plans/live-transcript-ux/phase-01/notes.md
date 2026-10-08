<!-- ccg-shared-version: 10.6.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Updated characterization tests in `tests/test_streaming_backends.py` to assert raw tool payload retention.
- Added comprehensive nested payload fixture tests for Claude, Codex, Pi, and Agy.
- Tested value preservation for nested dicts, arrays, numbers, booleans, empty structures, null, and missing fields.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED: `uv run pytest -q tests/test_streaming_backends.py` failed with 8 failing tests due to missing tool payload normalization (`KeyError: 'input'`).
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Updated `src/openmcp/backends/claude.py` to copy `content_block.input` on `content_block_start` tool_use, and preserve `output`/`result` on `content_block_stop` without inventing missing output.
- Updated `src/openmcp/backends/codex.py` to copy `item.input` on `item.started` tool_call and `item.output` on `item.completed` tool_call.
- Updated `src/openmcp/backends/pi.py` to copy `event.args` on `tool_execution_start`/`tool_call` and `event.result` on `tool_execution_end`/`tool_result` while keeping error normalization intact.
- Updated `src/openmcp/backends/agy.py` to copy `arguments` (and fallback `input`/`args`) on `tool.started` and normalize `output`/`result` to `data.output` on `tool.completed`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN: `uv run pytest -q tests/test_streaming_backends.py` passed 9/9 tests.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Added `test_dashboard_job_output_preserves_nested_tool_payloads` in `tests/test_dashboard.py` verifying provider event -> normalized event -> StreamRecorder -> SQLite `job_stream_events.data_json` -> dashboard REST `/output` API.
- Verified exact type preservation (nested objects, lists, numbers, booleans, empty structures, null, and missing fields) across database persistence and HTTP output.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN: `uv run pytest -q tests/test_dashboard.py -k "tool_payloads"` passed.
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- Narrowed security regression assertions in `tests/test_execution.py` and `tests/test_dashboard.py` to allow approved tool payloads to persist and display while keeping prompts, thinking/reasoning, diagnostic traces, and subagent transcripts strictly excluded.
- Verified tool payloads never enter `job.result.text` or assistant text.
- Verified SSE updates channel remains cursor-notification only (`data: {"cursor": ...}`) and never exposes tool or forbidden tokens.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN: Full verification commands passed:
  - `uv run pytest -q tests/test_streaming_backends.py` (9 passed)
  - `uv run pytest -q tests/test_streaming_backends.py tests/test_execution.py tests/test_dashboard.py` (106 passed)
  - `uv run pytest -q tests/test_execution.py -k "attempt or stream or quota or truncat or cancel or retry or provider"` (21 passed)
  - `uv run pytest -q tests/test_dashboard.py -k "output or stream or security"` (10 passed)
  - `git diff --check` (clean)
- Root cause (bugfix only): n/a

## Review Fix

### Decisions made
- In `src/openmcp/backends/claude.py`, removed all `content_block_stop` output and result extraction fallbacks; tool completion now emits status only.
- Added regression test `test_claude_streaming_content_block_stop_output_ignored` in `tests/test_streaming_backends.py` confirming `content_block_stop` output and result fields are excluded.
- In `src/openmcp/backends/agy.py`, removed speculative `input` and `args` fallback aliases; supported only the observed `arguments` input field.
- Adjusted synthetic test fixtures in `tests/test_streaming_backends.py` and added assertions verifying unproven `input` and `args` fields are ignored.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN: Verification commands passed:
  - `uv run pytest -q tests/test_streaming_backends.py` (10 passed)
  - `uv run pytest -q tests/test_streaming_backends.py tests/test_execution.py tests/test_dashboard.py` (107 passed)
  - `git diff --check` (clean)
- Root cause (bugfix only): Claude `content_block_stop` included speculative output/result extraction logic not present in real provider events. Agy accepted unproven `input`/`args` aliases rather than strictly adhering to observed `arguments` fields.
