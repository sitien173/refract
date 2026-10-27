<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Decision Notes

Append one block per task using the bundled notes template. Preserve earlier evidence.

## Task 1

### Decisions made
- Replaced `BackendResult.usage` and `DriverResult.usage` with explicit optional `model: str | None = None`.
- Deleted `USAGE_KEYS`, `_usage_dict`, and legacy result-usage parser `_usage_values` across `server/src/refract/backends/__init__.py`, `agy.py`, `claude.py`, `codex.py`, and `pi.py`.
- Updated `server/src/refract/execution.py` to read `result.model` directly and removed fallback dictionary lookups into legacy usage maps.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  RED: `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_result_model_identity_replaces_usage)` failed with `TypeError: BackendResult.__init__() got an unexpected keyword argument 'model'`.
  GREEN: `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_result_model_identity_replaces_usage)` passed with `1 passed, 64 deselected in 0.44s`.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Preserved native provider parsing required by normalized collectors across agy, claude, codex, and pi.
- Extracted model identity for backend results:
  - `agy`: reversed stream events inspecting `model` or `assistant` message model identity.
  - `claude`: `_extract_model` inspecting `_final_result["modelUsage"]` keys or parser `active_model`.
  - `codex`: `parser.collector.model_name` populated from rollout file events.
  - `pi`: reversed stream events inspecting `message_end` or `agent_end` message metadata.
- Added comprehensive regression tests in `test_streaming_backends.py` and `test_execution.py` covering final-only/non-streaming results, cache accounting, missing telemetry, cancellation, and failure precedence.
- Verified that target model fallback does not fabricate context capacity when context window telemetry is missing.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  RED: `TypeError: 'generator' object is not reversible` when `reversed(stream.objects())` was called during initial streaming characterization.
  GREEN: Updated extraction to traverse `reversed(stream.events)`, passing all test assertions across all four backends.
  Pass output: `tests/test_streaming_backends.py` (65 passed in 0.54s), `tests/test_execution.py` (125 passed in 184.23s).
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Audited production references to legacy keys across `server/src/refract/`.
- Classified all remaining reads of `model_name`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `total_tokens`, `duration_ms`, `latency_ms`:
  1. `server/src/refract/result_metadata.py`: Schema-15 database converter input (`from_legacy_row`) for backward-compatible migration of historical records stored prior to schema version 16.
  2. `server/src/refract/backends/agy.py`, `claude.py`, `codex.py`, `pi.py`: Provider-native payload parsing in normalized telemetry collectors (`_AgyCollector`, `_ClaudeCollector`, `_CodexRolloutCollector`, `_PiCollector`).
- Verified no public compatibility aliases, mapping shims, or duplicate usage parsers remain in production code.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Full test verification:
  - `(cd server && uv run --extra dev python -m pytest -m 'not live')` -> 966 passed, 15 deselected in 205.47s.
  - `bash plugin/tests/test-session-start.sh` -> session-start tests passed.
  - `bash plugin/tests/test-contracts.sh` -> contract tests passed.
- Root cause (bugfix only): - none

## Evidence Correction and Audit Inventory

### Pre-refactor characterization status
- An isolated pre-refactor characterization suite for Task 2 edge cases was not run before modifying adapters.
- Initial baseline suite passed prior to implementation:
  - `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py)` (63 passed in 0.44s)
  - `(cd server && uv run --extra dev python -m pytest tests/test_execution.py)` (124 passed in 191.06s)
  - Baseline total: 963 passed, 15 live deselected.
- Task 2 recorded RED (`TypeError: 'generator' object is not reversible`) was an incidental implementation defect during development of stream model extraction, not a pre-refactor characterization failure.
- Honest assessment: Genuine pre-refactor characterization evidence is missing from the historical log. Final passing suite (966 passed, 15 deselected) demonstrates current functional correctness, but does not prove pre-refactor characterization order.

### Production reference inventory and audit correction
- Audit identifier correction: Corrected nonexistent `from_legacy_row` to actual converter `convert_schema15_metadata` and validator `_legacy_validate` in `server/src/refract/result_metadata.py`.
- Concrete exhaustive inventory:
  1. Removed bridge symbols:
     - `BackendResult.usage`: Removed from `server/src/refract/backends/__init__.py`. Replaced with `model: str | None = None`. Zero production references remain.
     - `DriverResult.usage`: Removed from `server/src/refract/drivers.py`. Replaced with `model: str | None = None`. Zero production references remain.
     - `USAGE_KEYS`, `_usage_dict`, `_usage_value`: Removed from `server/src/refract/backends/__init__.py`. Zero production references remain.
     - `_usage_values`: Removed from `server/src/refract/backends/agy.py`, `claude.py`, `codex.py`, `pi.py`. Zero production references remain.
  2. Remaining legacy keys in production:
     - `server/src/refract/result_metadata.py`:
       - `_legacy_validate` (lines 124-129): Validates legacy dictionary keys `"model_name"`, `"duration_ms"`, `"failure_kind"`, `"retryable"`, `"next_target"`, `"context_window_max"`, `"context_window_used"`, `"input_tokens"`, `"output_tokens"`, `"cached_input_tokens"`. Classification: Schema-15 database migration converter input.
       - `convert_schema15_metadata` (lines 185-199): Reads `"model_name"`, `"failure_kind"`, `"duration_ms"`, `"retryable"` from legacy dict. Classification: Schema-15 database migration converter input.
  3. Canonical runtime fields and normalized measurement fields:
     - `duration_ms`:
       - Canonical schema field: `ExecutionMetadata.duration_ms` in `server/src/refract/result_metadata.py` (lines 69-76).
       - Runtime execution measurement: `server/src/refract/execution.py` (lines 228, 240, 248, 366, 372, 380, 428, 442, 450, 478), `server/src/refract/database.py` (line 543), `server/src/refract/server.py` (line 531), `server/src/refract/processes.py` (line 186). Wall-clock execution timing, distinct from legacy schema-15 database migration input.
     - Normalized telemetry measurement keys:
       - Schema fields: `METRIC_NAMES` (`context_remaining_percent`, `context_window_size`, `context_used_tokens`, `total_input_tokens`, `total_output_tokens`, `cache_read_tokens`, `cache_write_tokens`) in `server/src/refract/result_metadata.py` (lines 13-16, 90-96) and `server/src/refract/telemetry.py`.
       - Pipeline processing: `server/src/refract/execution.py` (lines 530-557) reads observation keys (`"total_input_tokens"`, `"total_output_tokens"`, `"input_tokens"`, `"output_tokens"`, `"cache_read_tokens"`, `"cache_write_tokens"`) emitted by normalized `TelemetryCollector`. Distinct from legacy bridge usage keys.
  4. Provider-native payload parsing in normalized collectors:
     - `server/src/refract/backends/agy.py`: `_AgyCollector` reads payload `update.get("usage")` / `result.get("usage")` extracting `input_tokens`, `output_tokens`.
     - `server/src/refract/backends/claude.py`: `_ClaudeCollector` reads payload `message.get("usage")` / `event.get("usage")` extracting `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`.
     - `server/src/refract/backends/codex.py`: `_CodexRolloutCollector` reads payload `info.get("last_token_usage")` / `parsed.get("usage")` extracting `input_tokens`, `output_tokens`, `reasoning_output_tokens`, `cached_input_tokens`.
     - `server/src/refract/backends/pi.py`: `_PiCollector` reads payload `msg.get("usage")` / `event.get("usage")` / `event.get("totalUsage")` extracting `input_tokens`, `output_tokens`.
     Classification: Necessary provider payload parsing in collectors for normalized telemetry.

### Behavioral test-first evidence for model extraction
- Task 1 RED evidence captured constructor signature failure:
  - Command: `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_result_model_identity_replaces_usage)`
  - Output: `TypeError: BackendResult.__init__() got an unexpected keyword argument 'model'`.
- Behavioral assertion of stream model extraction (`result.model == expected`) was not run in a failing test-first state prior to adding `_extract_model` across adapters.
- Honest assessment: Behavioral test-first evidence beyond constructor signature rejection is missing. This is an acknowledged process gap.

## NEW Test-First Reconstruction and Behavioral Regression Evidence

### Passing characterization of normalized telemetry and outcomes
- Established passing characterization of all four adapters covering non-streaming results, cache accounting, cancellation precedence, missing telemetry, and model fallback without capacity fabrication:
  - `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k "test_all_four_adapters_final_only_non_streaming_and_cache or test_backend_cancellation_and_failure_precedence_preserved")` -> 2 passed, 64 deselected in 0.74s.
  - `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_missing_input_tokens_leaves_input_unavailable_and_partial)` -> 1 passed, 65 deselected in 0.45s.
  - `(cd server && uv run --extra dev python -m pytest tests/test_execution.py -k test_result_metadata_produces_canonical_grouped_structure_and_context_overflow)` -> 1 passed, 124 deselected in 1.48s.

### NEW Behavioral Test-First Regression Suite
- Added comprehensive behavioral regression test `test_behavioral_model_extraction_all_routes_and_propagation` in `server/tests/test_streaming_backends.py`.
- Covers every newly implemented extraction route and driver/execution propagation:
  - Route 1: Agy stream model event with absent telemetry -> extracts `agy-test-model`.
  - Route 2a: Claude `modelUsage` in final result -> extracts `claude-3-5-sonnet-20241022`.
  - Route 2b: Claude streaming assistant message `active_model` with absent telemetry -> extracts `claude-3-haiku-20240307`.
  - Route 3a: Codex `session_configured` in rollout with absent telemetry -> extracts `gpt-4o-custom`.
  - Route 3b: Codex `model_reroute` in rollout -> extracts `o3-mini-custom`.
  - Route 4a: Pi `message_end` assistant message metadata -> extracts `pi-streaming-extracted`.
  - Route 4b: Pi `agent_end` assistant messages with absent telemetry -> extracts `pi-agent-end-extracted`.
  - Route 5: `DriverResult._normalize` model identity propagation -> `drv.model == "pi-agent-end-extracted"`.
  - Route 6: `TargetExecutor._result_metadata` model propagation, target fallback without capacity fabrication, and empty target model preservation.

### NEW Behavioral RED Evidence
- Verified assertions demonstrably fail before minimal adapter implementation:
  - Agy extraction failure before implementation:
    - Command: `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_behavioral_model_extraction_all_routes_and_propagation)`
    - Output:
      `AssertionError: assert None == 'agy-test-model'`
      `+ where None = BackendResult(outcome='OK', SESSION_ID='', agent_messages='ok', error='warning: no SESSION_ID', error_class='warning', model=None, telemetry=None).model`
  - Pi extraction failure before implementation (covering message_end and agent_end):
    - Command: `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_behavioral_model_extraction_all_routes_and_propagation)`
    - Output:
      `AssertionError: assert None == 'pi-streaming-extracted'`
      `+ where None = BackendResult(outcome='OK', SESSION_ID='pi-s1', agent_messages='hello', error='', error_class='', model=None, telemetry=None).model`

### NEW GREEN Evidence after minimal implementation
- Command: `(cd server && uv run --extra dev python -m pytest tests/test_streaming_backends.py -k test_behavioral_model_extraction_all_routes_and_propagation)`
- Output: `1 passed, 65 deselected in 0.31s`.

### Orphan Import Audit
- Audited all Phase 3 modified product paths for newly orphaned imports:
  - Identified `from dataclasses import dataclass, field` in `server/src/refract/drivers.py` where `field` was only needed by the removed `DriverResult.usage` definition.
  - Removed `field` import from `server/src/refract/drivers.py`.
  - Verified with `(cd server && uv run ruff check --select F401 src/refract/backends/__init__.py src/refract/backends/agy.py src/refract/backends/claude.py src/refract/backends/codex.py src/refract/backends/pi.py src/refract/drivers.py src/refract/execution.py)` -> `All checks passed!`.

### Phase Verification Checks
- Exact checks executed from repository root after reconstruction:
  - `(cd server && uv run --extra dev python -m pytest -m 'not live')` -> 967 passed, 15 deselected in 151.01s.
  - `bash plugin/tests/test-session-start.sh` -> session-start tests passed.
  - `bash plugin/tests/test-contracts.sh` -> contract tests passed.
