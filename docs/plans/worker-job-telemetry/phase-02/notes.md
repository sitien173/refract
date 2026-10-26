<!-- refract-shared-version: 2.0.0 -->

# Phase 2 — Decision Notes

<!--
Worker Notes template. Copy to docs/plans/<slug>/phase-<NN>/notes.md, fill the
heading, then append one `## Task <M>` block per task. Keep the file; never
overwrite earlier task blocks. Empty sub-sections = `- none`. Every task gets a
block even if all `none`.
-->

## Task 1

### Decisions made
- Extended `BackendResult` with optional `telemetry: dict[str, Any] | None = None` to propagate normalized telemetry across backend results without altering legacy `usage` dictionary.
- Updated sanitized fixtures (`claude.jsonl`, `codex.jsonl`, `agy.jsonl`) with multi-response structures, retaining verified `pi.jsonl` multi-response structure.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Each backend's legacy extraction remains preserved for backwards compatibility while normalized telemetry is exposed via `result.telemetry`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added `test_backend_result_telemetry_field`, `test_multi_response_pi_telemetry_exceeds_final_message_alone`, `test_claude_cache_reads_and_writes_enter_normalized_input_once`, `test_codex_cached_input_not_added_twice`, and `test_agy_final_totals_do_not_duplicate_prior_step_consumption`. Confirmed RED on all 5 tests. `test_backend_result_telemetry_field` passed once `BackendResult.telemetry` was added.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Implemented Claude telemetry collector reconciling `assistant` events with final `result` usage and active model capacity lookup in `modelUsage`.
- Implemented Pi telemetry collector aggregating authoritative `message_end` assistant events, deduplicating repeated `turn_end` events by `responseId`, and ignoring partial streaming updates.
- Normalized input for Claude and Pi to include separate cache read/write components once.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Active model in Claude is identified from assistant messages, falling back to solitary `modelUsage` entry; unrelated model keys in multi-entry `modelUsage` are rejected.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_claude_capacity_not_selected_arbitrarily`, `test_pi_lifecycle_duplicates_do_not_double_count`, `test_claude_cache_reads_and_writes_enter_normalized_input_once`, and `test_multi_response_pi_telemetry_exceeds_final_message_alone` failed initially (RED) and passed after Claude/Pi collector implementations (GREEN).
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Implemented Codex telemetry collector in `_EventParser`.
- Derived occupied context for Codex without double-counting cached input.
- Implemented Agy telemetry collector in `_EventParser`.
- Reconciled Agy completed step usage with cumulative result totals.
- Attached `result.telemetry` on Codex and Agy execution results.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Codex input already includes cached tokens.
- Agy input already includes cache read tokens.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_codex_cached_input_not_added_twice` and `test_agy_final_totals_do_not_duplicate_prior_step_consumption` were RED and became GREEN after adapter collector implementation.
- Root cause (bugfix only): - none

## Task 4

### Decisions made
- Added compaction tests for shrinking context snapshots.
- Added tests for repeated cumulative replacements.
- Verified missing baselines produce incomplete totals.
- Verified pre-completion telemetry persistence for streaming jobs.
- Verified session resumption isolates per-job consumption.
- Verified parsing failures preserve backend outcomes.
- Verified no-emitter execution across all adapters.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Adapters preserve normalized telemetry without emitters.

### Follow-ups for human
- none

### Test evidence
- Added `test_repeated_cumulative_snapshots_replace_not_add`.
- Added `test_context_snapshot_shrinks_after_compaction_without_reducing_consumption`.
- Added `test_missing_baselines_produce_explicit_incomplete_totals`.
- Added `test_synthetic_multi_response_persists_telemetry_before_completion`.
- Added `test_resumed_session_history_is_not_counted_as_subsequent_job_consumption`.
- Added `test_no_emitter_execution_returns_normalized_telemetry`.
- Added `test_parsing_failures_leave_text_and_outcome_unchanged`.
- All tests passing.
- Root cause (bugfix only): - none

## Review Cycle 2 Fixes

### Decisions made
- Scoped Pi no-ID deduplication to actual turns by tracking turn lifecycle boundaries (`turn_start` resets active turn completion state; repeated `message_end` or `turn_end` within the turn is deduplicated).
- Added `_parse_token_component` in Claude and Pi to distinguish invalid token components (negative, bool, non-finite, string) from legitimate omitted/zero fields. Malformed cache components preserve unknown normalized input (`norm_in = None`) and mark completeness partial.
- Pi `usage.totalTokens` is treated strictly as response usage, never labeled reported context; context is derived only when retained components are established (`norm_in is not None`), otherwise left unavailable.
- Separated emission of reported consumption (`quality="reported"`) from derived context snapshot observations (`quality="derived"`) across all four adapters (`claude`, `pi`, `codex`, `agy`) to prevent derived context quality from downgrading consumption metrics in execution.
- Removed extra EOF blank lines in touched test files.

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
  - `cd server && uv run pytest tests/test_streaming_backends.py -k "test_pi_no_id_lifecycle_scoped_to_actual_turns_and_dedups_repeated_message_end or test_claude_and_pi_malformed_cache_preserves_unknown_normalized_input or test_pi_total_tokens_never_labeled_reported_context_and_derivation_provenance"`
    - RED Failure 1: `tests/test_streaming_backends.py:2071: AssertionError: assert 200 == 450`
    - RED Failure 2: `tests/test_streaming_backends.py:2098: AssertionError: assert 100 is None`
    - RED Failure 3: `tests/test_streaming_backends.py:2206: AssertionError: assert 'reported' == 'derived'`
    - GREEN: 3 passed in 0.45s.
  - `cd server && uv run pytest tests/test_execution.py -k "test_real_adapter_observations_through_execution_persist_reported_consumption_alongside_derived_context"`
    - RED Failure: `tests/test_execution.py:4658: AssertionError: assert 'derived' == 'reported'` for claude, pi, codex, agy.
    - GREEN: 4 passed in 4.22s.
  - Full suite verification: `cd server && uv run pytest` -> 692 passed, 11 deselected in 123.08s.
- Root cause (bugfix only):
  - Finding 1: Pi `turn_counter` was unconditionally incremented on `message_end` without turn boundary tracking, double-counting repeated `message_end` and discarding subsequent no-ID turns because `self.turn_counter` matched `recorded_turns`. Fixed by tracking `turn_start` and turn completion lifecycle.
  - Finding 2: `_as_int` treated negative/bool/non-finite as `None`, which `(cr or 0)` turned into `0`, silently yielding complete input. Fixed by detecting present invalid components and setting `norm_in = None`.
  - Finding 3: `pi.py` used `u.get("totalTokens")` as `context_used_tokens` with `source="provider", quality="reported"`. Fixed by deriving context only when retained components are established and setting `quality="derived", source="derived"`.
  - Finding 4: All adapters emitted consumption and context in a single event with `quality="derived"`, causing `execution.py` to record consumption with `derived` quality. Fixed by emitting consumption with reported quality separately from derived context observations.


