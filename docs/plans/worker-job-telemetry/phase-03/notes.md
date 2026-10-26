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
