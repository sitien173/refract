# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Removed capabilities from the Python target response model.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Target health and capacity fields remain unchanged.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New response assertions failed in three tests; `uv run pytest tests/test_server.py tests/test_logging.py tests/test_dashboard.py` passed with 43 tests.

## Task 2

### Decisions made
- Strip capability keys from existing and incoming target tables.

### Spec deviations
- none

### Tradeoffs accepted
- Legacy TOML input remains loadable before and after writes.

### Assumptions
- Capability keys are removed only from target tables.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Config writer regression reproduced a retained capability key; focused Python adapter suite passed with 44 tests.

## Task 3

### Decisions made
- Removed the capability field and column from dashboard types and views.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Target health, capacity, and model columns remain unchanged.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Web tests failed in three target-view cases after capability fixtures were removed; `npm --prefix web test -- --run` passed with 145 tests.

## Task 4

### Decisions made
- Removed capability declarations from supported documentation and fixtures.

### Spec deviations
- none

### Tradeoffs accepted
- Generated asset filenames changed through the normal Vite build.

### Assumptions
- Phase 1 legacy capability fixtures remain necessary for compatibility coverage.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `npm --prefix web run build` completed successfully and regenerated dashboard assets.
