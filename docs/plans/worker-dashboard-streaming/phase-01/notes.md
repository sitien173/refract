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
