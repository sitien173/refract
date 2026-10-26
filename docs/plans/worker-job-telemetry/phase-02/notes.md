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

