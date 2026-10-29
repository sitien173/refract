# Phase 2 Decision Notes

## Task 1

### Decisions made
- Kept context resolution in `TelemetryAccumulator.snapshot()` so provider/configuration precedence is shared by live, retry, and terminal paths.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- A valid provider context-used observation remains authoritative even when its quality is `derived`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added resolution tests; initially failed because the accumulator had no configured-capacity binding API. After implementing binding/resolution, focused tests passed (`4 passed`).

## Task 2

### Decisions made
- Capacity fallback is represented in existing measurements: configured capacity uses source `target_config`; cumulative usage uses source `derived` and quality `estimated`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing completed and active total measurements provide the authoritative totals; cache counters are excluded.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Confirmed configured-capacity tests failed before implementation (missing `set_configured_capacity`), then passed after adding centralized resolution. Tests cover missing totals, known zero, provider usage precedence, override of provider capacity/percentage, and clamping.

## Task 3

### Decisions made
- Bind snapshotted selected-target capacity at execution selection, clear stale provider context, and persist the initial capacity measurement before invocation telemetry.
- `_safe_telemetry_dump` now retains capacity-only state.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Target configuration is immutable in the execution plan, so the selected plan target is the sole capacity source for this execution.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Initial full suite found five obsolete assertions expecting invalidated context to remain unavailable despite known cumulative totals. Updated only these approved expectations to assert explicitly estimated fallback. Full suite then passed: 1238 passed, 23 skipped, 15 deselected.

## Task 4

### Decisions made
- Retained backend provenance and quality; existing invalidation boundaries now naturally expose estimated fallback without converting estimates to provider snapshots.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing persistence merge and metadata projections retain the measurement fields and provenance without schema changes.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Focused precedence/missing/bounds tests passed (`4 passed`). Fresh complete verification before follow-up cycle: `cd server && uv run pytest -q` -> 1240 passed, 23 skipped, 15 deselected.

## Task 5 — Cycle 1 specification fixes

### Decisions made
- On hydration, discard only fallback usage/remaining identified by source `derived` plus quality `estimated`; retain genuine backend snapshots, including quality `derived`.
- Treat a hydrated `target_config` capacity as configured state rather than native provider capacity, so clearing configuration removes the old value.
- Do not replay backend-returned fallback measurements as native context observations.
- Preserve selected-target capacity in environment/configuration failure result metadata.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The `derived` source plus `estimated` quality pair identifies resolver fallback; other provenance remains eligible as a backend observation.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New hydration regressions failed before the fix: restored usage remained 120 rather than tracking the updated total 60, and clearing capacity retained 1000. All 3 focused hydration/provider invalidation tests passed after the fix.
- RED -> GREEN: Added selected-target capacity integration for streaming and final-result telemetry, asserting persisted capacity before backend invocation and final estimated usage. Added configuration-failure metadata coverage. Focused batch passed: 7 passed.
- Fresh full verification after cycle 1: `cd server && uv run pytest -q` -> 1247 passed, 23 skipped, 15 deselected.

## Task 6 — Cycle 2 specification fixes

### Decisions made
- On hydration, clear a remaining percentage from source `derived` when its serialized capacity is the `target_config` override; preserve explicit provider-originated percentages regardless of reported/derived quality.
- When usage and capacity internally calculate a percentage, propagate `estimated` quality from estimated usage. Explicit supplied provider percentages remain authoritative.
- Exercise non-streaming DriverResult replay with fallback-like derived/estimated measurements to verify they are not promoted over freshly resolved totals.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Resolver percentages use source `derived`; provider-supplied remaining percentages retain backend source provenance.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added override-clear roundtrip and estimated-usage quality tests. Before the fix, clear left 75% remaining despite unavailable capacity, and calculated remaining quality was `derived` rather than `estimated`; both failed. All 3 focused regressions then passed.
- RED -> GREEN: Extended streaming/non-streaming selected-capacity integration coverage with fallback-like DriverResult context measurements; both parametrized cases passed and retained usage resolved from totals (non-streaming replay did not promote stale fallback).
- Fresh full verification: `cd server && uv run pytest -q` -> 1250 passed, 23 skipped, 15 deselected.
