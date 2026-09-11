<!-- ccg-shared-version: 10.5.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Added characterization fixtures in tests/test_streaming_backends.py for Claude, Codex, Pi, and Agy.
- Verified exclusion of secrets, reasoning, and tool arguments/results from normalized stream.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Emitter callback is synchronous and optional on provider params dataclasses.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_streaming_backends.py` failed with 4 errors: `TypeError: *Params.__init__() got an unexpected keyword argument 'emitter'`.
- Root cause (bugfix only): not applicable

## Task 2

### Decisions made
- Added optional `emitter` callback parameter to `ClaudeParams`, `CodexParams`, `PiParams`, and `AgyParams`.
- Configured Claude to use stream-json and `--include-partial-messages`.
- Configured Agy to use stream-json.
- Parsed and normalized assistant text deltas and safe tool lifecycle events across all adapters.
- Preserved authoritative final result extraction and session extraction unchanged.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Adapters execute on worker threads and pass normalized dictionaries to emitter.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_streaming_backends.py` passed all 4 tests after implementing provider streaming normalization.
- Root cause (bugfix only): not applicable

## Task 3

### Decisions made
- Added bridge tests in `tests/test_execution.py`: `test_stream_bridge_blocking_backpressure_and_sentinel_drain`, `test_stream_bridge_cancellation_drains_accepted_events`, `test_stream_bridge_thread_ownership_no_sqlite_on_provider_thread`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- StreamBridge uses a 256-slot asyncio bounded queue with blocking producer backpressure via `asyncio.run_coroutine_threadsafe`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_execution.py -k "test_stream_bridge"` failed with `ImportError: cannot import name 'StreamBridge'`, then passed all 3 tests after implementing `StreamBridge` in `src/openmcp/drivers.py`.
- Root cause (bugfix only): not applicable

## Task 4

### Decisions made
- Implemented `StreamBridge` consumer draining and `StreamRecorder` batch flushing in `TargetExecutor.execute()`.
- Guaranteed attempt ordering: bridge consumer drained, recorder closed and flushed prior to target lifecycle finish and job state finalization.
- Added pre-execution structured-mode capability check `supports_structured_streaming` on `DriverRegistry`.
- Cached capability results per resolved executable path (`shutil.which(target.backend)`).
- Implemented capability detection by checking provider CLI `--help` for required flags (`stream-json` & `--include-partial-messages` for Claude, `stream-json` for Agy, `--json` for Codex, `--mode` for Pi).
- When capability is unsupported or emitter is None, used final-only fallback without structured flags or post-submission prompt retries.
- Verified fake drivers in async tests emit from worker threads via `asyncio.to_thread` to adhere to provider worker thread contract.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Provider CLI processes execute in worker threads where synchronous emitter submits safely to the bounded asyncio queue.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run pytest tests/test_execution.py -k "test_capability_check_before_submission_with_final_only_fallback"` verified caching per resolved executable path and final-only fallback (emitter=None) without prompt retry.
- RED -> GREEN (blocking defect fix): `uv run pytest tests/test_execution.py -k test_detect_structured_mode_invokes_help_probe_and_detects_support` failed with `AssertionError: assert False is True` because missing `import subprocess` caused `subprocess.run` to raise `NameError` which was swallowed by exception handling. After adding `import subprocess`, the default `--help` probe executes, detects supported output, and passes.
- Full suite `uv run pytest tests/test_streaming_backends.py tests/test_execution.py tests/test_live_backends.py -m 'not live'` passed 48 tests.
- Root cause (bugfix only): Test fake driver in `test_accepted_events_flush_before_lifecycle_completion` called synchronous emitter directly on the asyncio event loop thread instead of a worker thread, deadlocking `asyncio.run_coroutine_threadsafe(...).result()`. Fixed by emitting via `asyncio.to_thread(worker)`.
- Root cause (blocking defect): `src/openmcp/drivers.py` was missing `import subprocess`, causing `_detect_structured_mode()` to raise `NameError` on `subprocess.run()`, which was caught and caused default capability probes to return `False`. Fixed by importing `subprocess`.
- Gap resolved: `DriverRegistry.supports_structured_streaming()` now inspects resolved executable path capability via `--help` subprocess probe, caches per executable path, and falls back cleanly to final-only invocation without prompt retries.

## Task 5

### Decisions made
- Parsed Agy terminal assistant content separately from raw JSON tool events, metadata lines, and internal log output, ensuring fixture secrets never reach `result.agent_messages` or `job.result.text`.
- Supported Pi `--mode json` `message_update.assistantMessageEvent` text deltas and `tool_execution_start`/`tool_execution_end` shapes; updated `PI_JSON_FIXTURE` to current representative shapes.
- Unwrapped Claude top-level `stream_event` envelopes to inspect nested `event` for streaming normalization and terminal `result` extraction; updated `CLAUDE_STREAM_JSON_FIXTURE` accordingly.
- Probed `codex exec --help` instead of top-level `codex --help` for Codex capability detection, asserting support from `exec --help` containing `--json` while top-level help lists commands without `--json`.
- Maintained `entity_state` across Agy continuations in `_execute_sync`, producing unique synthetic assistant entity IDs (`msg-1`, `msg-2`, etc.) across real adapter continuations while preserving session and final result extraction.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Agy CLI output format when streaming uses stream-json events interspersed with possible metadata or terminal strings; assistant messages are isolated from tool events.

### Follow-ups for human
- none

### Test evidence
- RED:
  - `test_claude_streaming_normalization`: failed with `assert 0 >= 2` when stream_event envelopes were not unwrapped.
  - `test_pi_streaming_normalization`: failed with `assert 0 >= 1` when real Pi message_update and tool_execution shapes were unrecognized.
  - `test_agy_streaming_normalization`: failed with `assert 'secret_token_val' not in result.agent_messages` because raw JSON output leaked into agent messages.
  - `test_agy_continuations_unique_synthetic_entities`: failed with `AssertionError: assert 'msg-1' != 'msg-1'` when continuation entity IDs collided.
  - `test_codex_capability_probes_exec_subcommand`: failed with `assert False is True` when top-level help without `--json` was probed.
- GREEN:
  - All 5 tests passed after surgical updates to `claude.py`, `pi.py`, `agy.py`, and `drivers.py`.
  - Full suite `uv run pytest tests/test_streaming_backends.py tests/test_execution.py tests/test_live_backends.py -m 'not live'`: 50 passed, 3 deselected in 11.39s.
  - `git diff --check`: Clean, zero whitespace issues.
- Root causes:
  - (1) Agy raw stdout and log fallback reached `agent_messages` directly, including tool arguments and outputs.
  - (2) Pi backend and fixture used flattened shapes rather than `message_update.assistantMessageEvent` and `tool_execution_*`.
  - (3) Claude stream-json envelopes wrapped partial messages under `stream_event.event`.
  - (4) Codex capability probed `codex --help` rather than `codex exec --help`.
  - (5) Agy adapter continuations re-instantiated local counter, reusing `msg-1`.
