<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Decision Notes

Append one Task block per task using plugin/shared/notes-template.md. Preserve RED and GREEN evidence and capability limitations.

## Task 1

### Decisions made
- Documented verified CLI versions and telemetry capabilities in `server/CLI_ARGUMENTS.md`.
- Documented observed, fixture-only, and unverified telemetry measurements for Codex, Claude Code, Pi, and Antigravity.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_cli_arguments_documents_telemetry_capabilities_and_versions` in `server/tests/test_telemetry.py` failed RED on missing capability documentation and verified version strings (`AssertionError: assert 'agy 1.4.7' in content`), then passed GREEN after updating `server/CLI_ARGUMENTS.md`.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Implemented `_CodexRolloutCollector` in `server/src/refract/backends/codex.py` with bounded exact-session matching.
- Polled incrementally on events without launching a background watcher daemon.
- Baselined cumulative counters safely in resumed sessions and marked incomplete when baseline is missing.
- Invalidated stale context on compaction and model change.
- Tested identity mismatch, concurrent sessions, partial/malformed lines, file growth, rotation, truncation, missing files, and cancellation.

### Spec deviations
- none

### Tradeoffs accepted
- Used bounded 64KB reads up to 1MB total per invocation to prevent unbounded file reads.

### Assumptions
- Codex rollout lines conform to JSONL append-only format with `session_meta`, `event_msg`, and `token_usage_record`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_codex_rollout_missing_baseline_marks_incomplete` failed RED (`AssertionError: assert 'complete' == 'partial'`), then passed GREEN after implementing preflight baselining and missing baseline handling. `test_codex_rollout_cumulative_counter_baselining_in_resumed_session` failed RED (`ValueError: Invalid telemetry source: rollout`), then passed GREEN with valid source `"session"`.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Verified Pi JSON stream and session files do not expose context window capacity; left capacity null without launching extra model requests or RPC daemons.
- Handled explicit Agy context window size if present in step updates or results; left capacity null for default headless print mode.
- Added offline capability tests for Pi and Agy in `server/tests/test_streaming_backends.py`.
- Added opt-in live telemetry probe in `server/tests/test_live_backends.py` requiring explicit `REFRACT_LIVE_TELEMETRY_OPT_IN=1` and failing on missing prerequisites without running live requests.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Headless `agy --print` does not emit model context capacity unless explicitly provided in event metadata.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_agy_explicit_context_metadata_handled` failed RED (`AssertionError: assert None == 200000`), then passed GREEN after implementing explicit context metadata extraction in `step_update` and `result` in `server/src/refract/backends/agy.py`.
- Root cause (bugfix only): none
