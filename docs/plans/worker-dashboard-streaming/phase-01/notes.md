<!-- ccg-shared-version: 10.5.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Defined schema version 11 test assertions.
- Added cursor and retention test coverage.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED: 8 tests in tests/test_database.py failed with missing attributes and schema version 10.
- Root cause (bugfix only): not applicable

## Task 2

### Decisions made
- Added schema version 11 migration.
- Added JobStreamEvent and StreamTotals models.
- Added stream database methods to Database class.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN: 21 tests in tests/test_database.py passed.
- Root cause (bugfix only): not applicable

## Task 3

### Decisions made
- Added tests for batching, coalescing, and limits.
- Added tests for splitting and persistence failures.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED: tests/test_streaming.py failed with ModuleNotFoundError for openmcp.streaming.
- Root cause (bugfix only): not applicable

## Task 4

### Decisions made
- Implemented StreamRecorder with coalescing and bounds.
- Wired startup retention pruning to Runtime.start.
- Isolated persistence failures from worker results.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN: 40 tests in test_database.py, test_streaming.py, test_runtime.py passed.
- Root cause (bugfix only): not applicable

## Review Findings Fix

### Decisions made
- Added Database.stream_is_truncated method.
- Reconstructed durable truncation in StreamRecorder on initialization.
- Triggered flush immediately when text coalescing crosses 64 KiB.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED: test_recorder_64kib_batch_flush and test_recorder_reconstructs_durable_truncation_across_instances_and_reopen failed in tests/test_streaming.py, and test_stream_is_truncated_lookup failed in tests/test_database.py. GREEN: 42 tests in test_database.py, test_streaming.py, test_runtime.py passed.
- Root cause (bugfix only): StreamRecorder only checked numeric totals on init rather than existing truncation markers. Coalescing branch updated buffer bytes but bypassed batch threshold flush with continue.
