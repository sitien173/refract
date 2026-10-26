<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Decision Notes

Append one Task block per task using plugin/shared/notes-template.md. Preserve RED and GREEN evidence and capability limitations.

## Task 1

### Decisions made
- Documented verified CLI versions and telemetry capabilities in `server/CLI_ARGUMENTS.md`.
- Explicitly separated evidence levels: package/CLI documentation evidence, synthetic fixture-only testing, and runtime unverified/unavailable limitations.
- Documented capability limitations: Codex context capacity is null without external config; Pi context capacity is null without catalog/RPC; Agy capacity is null in headless print mode.
- Recorded live probe selectors (`server/tests/test_live_backends.py::test_live_telemetry_probe`) and marked opt-in only, not run.

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
- Replaced unbounded glob scan in `_find_exact_file` with genuinely bounded iterative directory traversal: max 50 entries, max depth 3, max 3 retries.
- Refused symlinks (`entry.is_symlink()`, `file_path.is_symlink()`), symlink escapes (`not file_path.resolve().is_relative_to(resolved_sessions_dir)`), and non-regular files (`not entry.is_file(follow_symlinks=False)`).
- Revalidated file identity across polls using device and inode (`st_dev`, `st_ino`) to detect rotation at equal or larger size.
- Emitted explicit context clear telemetry for every invalidation (compaction, model change, truncation, inode replacement).
- Isolated malformed lines, payload decode errors, and malformed cwd strings so worker execution and outcome remain unaffected.
- Derived occupied context strictly from latest turn usage (`norm_in + norm_out - reasoning_out`) with provenance `source="derived", quality="derived"`.
- Kept context capacity limit (`context_window_size`) unavailable null; removed unverified speculative schemas.
- Preferred invocation-local stream totals from `turn.completed`; in resumed sessions without safe baselines, preserved turn totals and marked completeness partial.

### Spec deviations
- none

### Tradeoffs accepted
- Bounded file discovery to 50 entries and 3 retries; after retry cap, no further disk scans are performed.

### Assumptions
- Codex rollout files contain append-only records with compaction markers (`context_compacted`) and metadata.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - `test_codex_discovery_bounded_entries_and_depth` failed RED (`AttributeError: '_CodexRolloutCollector' object has no attribute 'MAX_DISCOVERY_ENTRIES'`), passed GREEN after implementing bounded traversal constants and logic.
  - `test_codex_discovery_missing_file_retry_cap` failed RED (`AttributeError: '_CodexRolloutCollector' object has no attribute 'missing_discovery_retries'`), passed GREEN after adding retry cap.
  - `test_codex_discovery_refuses_symlinks_and_hostile_paths` failed RED (`AssertionError: assert PosixPath(...) is None`), passed GREEN after enforcing symlink and relative-path escape checks.
  - `test_codex_rollout_rotation_equal_size_revalidates_and_emits_invalidation` failed RED (`AttributeError: '_CodexRolloutCollector' object has no attribute 'file_ino'`), passed GREEN after tracking inode and dev.
  - `test_codex_resumed_session_without_baseline_marks_incomplete` passed GREEN verifying invocation-local totals and partial completeness.
  - `test_codex_fresh_session_cumulative_reconciles_complete` passed GREEN verifying fresh session reconciliation.
- Root cause (bugfix only): Unbounded glob scan traversed entire directory tree without entry limits or retry bounds.

## Task 3

### Decisions made
- Verified Pi JSON stream and session files do not expose context window capacity; left capacity null without launching extra model requests or RPC daemons.
- In Agy, strictly separated derived occupied context (`source="derived", quality="derived"`) from reported capacity (`quality="reported"`).
- Propagated explicit terminal capacity in Agy `result` through emitter.
- Handled nullable zero token counts correctly.
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
- RED -> GREEN:
  - `test_agy_context_provenance_separated_from_capacity` failed RED (`AssertionError: assert 'reported' == 'derived'`), passed GREEN after separating derived occupied context from reported capacity.
  - `test_agy_explicit_context_metadata_handled` passed GREEN verifying capacity extraction and remaining percentage derivation.
  - `test_pi_capacity_remains_null_offline` passed GREEN verifying Pi capacity remains unavailable null.
- Root cause (bugfix only): Agy previously set quality="reported" on occupied context when explicit window size was provided.


## Task 4 — Verified Codex token_count enrichment and capability correction

### Decisions made
- Used the version-matched public source at https://raw.githubusercontent.com/openai/codex/rust-v0.160.1/codex-rs/protocol/src/protocol.rs. It defines TokenUsageInfo with nested cumulative `total_token_usage`, latest `last_token_usage`, and optional `model_context_window`; TokenUsage contains input, cached input, output, reasoning output, and total counts. Verified installed CLI version with `codex --version` (`codex-cli 0.160.1`).
- Collect only exact-session `token_count` records. Never use cumulative totals for occupied context. Derive occupied context only from latest response (`input + output - reasoning`); report supplied capacity separately as reported. Later snapshots replace earlier snapshots.
- Open rollout reads with `O_NOFOLLOW`; verify opened descriptor device/inode and regular-file type to reject replacement/symlink targets discovered after initial path resolution.
- Updated capability documentation with source URL, evidence levels, limits, and without user-specific package paths. Pi absence is not asserted as verified; Agy capacity/occupied values are clearly fixture-only/unverified.
- Strengthened opt-in telemetry probe to require telemetry structure and at least one actual context/consumption measurement. Probe was not run.

### Spec deviations
- none

### Tradeoffs accepted
- The tested `input + output - reasoning` latest-response derivation is used as the occupancy proxy; no vendor status-line reserve adjustment is reproduced.
- Codex tagged source verifies the installed 0.160.1-compatible shape, but does not establish that every runtime rollout contains a token_count event. Runtime presence remains unverified without an authorized live probe.

### Assumptions
- `last_token_usage` is the response-local usage snapshot associated with the emitted token_count event; source struct semantics distinguish it from cumulative `total_token_usage`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: added nested-schema regression first; it failed because `context_window_size` remained null (`assert None == 64000`), then passed after exact-session parser support. Test proves capacity is reported, occupancy uses latest usage rather than cumulative totals, and later token_count snapshots replace context values.
- The first focused run also exposed test fixture escaping (`\\n` encoded a literal backslash); corrected fixture, then focused regression passed.
- `cd server && uv run pytest -q tests/test_streaming_backends.py tests/test_telemetry.py tests/test_live_backends.py` -> 79 passed, 15 deselected (before final duplicate-snapshot assertion).
- Final fresh `cd server && uv run pytest` -> 717 passed, 15 deselected.
- Opt-in live probe not run; no model requests made.

## Task 5 — Independent review blockers

### Decisions made
- Added an explicit `invalidate_context` telemetry event operation. Execution now invalidates only context measurements and immediately merges the snapshot, preserving observed consumption.
- Session identity changes clear the collector accumulator and emit persisted invalidation; initial empty-to-known session binding does not issue an unnecessary clear.
- Keep the exact-session rollout context as authoritative over turn-derived occupancy once a complete verified rollout snapshot is available; turn usage continues to update consumption.
- Carry device/inode identity captured while validating the discovery descriptor into the later read. The consuming descriptor must match it and independently validate the session header.
- Keep rollout snapshots pending until the bounded reader catches up to a complete line. If total-byte budget is exhausted with unread bytes, emit unavailable context instead of retaining a historical prefix as current. Invalidate a published snapshot when newly appended content is being reconciled.

### Spec deviations
- none

### Tradeoffs accepted
- For rollout files beyond the hard total-byte cap, context is unavailable rather than attempting unbounded tail scanning.

### Assumptions
- A complete `token_count` at the end of the currently readable exact-session rollout is the latest available context snapshot; capacity is reported only when that record includes a valid capacity.

### Follow-ups for human
- none

### Test evidence
- RED: execution integration test `test_context_invalidation_persists_nulls_without_clearing_consumption` failed with `assert 1060 is None`; execution ignored the invalidation event and retained prior context.
- RED: `test_codex_verified_rollout_context_wins_over_turn_consumption_snapshot` failed with `assert 5600 == 1060`; `turn.completed` replaced the verified response-local rollout snapshot.
- RED: `test_codex_rollout_session_switch_invalidates_context` failed with `assert 1060 is None`; `set_session_id` retained previous session context.
- RED: `test_codex_rollout_rejects_replacement_between_discovery_and_read` failed with `assert 200000 is None`; collector trusted the replacement path's current stat and consumed a file with no session header.
- RED: `test_codex_rollout_budget_exhaustion_invalidates_prefix_snapshot` failed with `assert 110 is None`; a prefix token_count was published despite unread history at the byte cap.
- GREEN: `cd server && uv run pytest -q tests/test_streaming_backends.py -k 'codex_rollout or verified_rollout_context_wins or session_switch_invalidates or rejects_replacement_between or budget_exhaustion_invalidates'` -> 17 passed, 44 deselected.
- GREEN: `cd server && uv run pytest -q tests/test_execution.py -k 'context_invalidation_persists_nulls or telemetry_updated_routes or telemetry_survives'` -> 3 passed, 119 deselected.
- An affected-module run initially found an extra initial-session invalidation in `test_backends_emit_derived_context_quality`; fixed so only an actual established-session switch invalidates. Final `cd server && uv run pytest -q tests/test_streaming_backends.py tests/test_execution.py` -> 183 passed.
- Final fresh `cd server && uv run pytest` -> 722 passed, 15 deselected.
- No live probes, model requests, credential reads, conversation reads, or transport changes.
- Final rerun after the total-byte-budget lifecycle adjustment: affected modules 183 passed; full suite 722 passed, 15 deselected in 124.47s.
