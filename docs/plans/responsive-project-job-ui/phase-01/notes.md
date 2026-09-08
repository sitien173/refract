<!-- ccg-shared-version: 10.4.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Supported priority levels (primary, secondary, tertiary, optional) with optional defaulting to hidden.
- Mapped minWidth and width metadata to colgroup elements and priority classes to col, th, td.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Columns without explicit priority default to primary.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: DataGrid.test.jsx failed initially due to missing priority classes, missing hidden default for optional columns, and missing col minWidth handling. Passed after updating DataGrid.jsx, LoadingRows.jsx, and app.css (3 passing tests).
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Implemented three-state sort cycling (none -> asc -> desc -> none).
- Implemented stable sorting fallback by original row index to preserve source order on tie breaks.
- Empty values (null, undefined, '') sort consistently to the end in ascending order.
- Provided both controlled and uncontrolled state support for sorting and column visibility.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Source row objects are not modified during sorting operations.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added 6 tests in DataGrid.test.jsx for cycling, aria-sort, stable sort order, non-mutation of source rows, empty value handling, and controlled/uncontrolled state. Verified all 9 tests pass.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Added accessible dropdown menu for column visibility with keyboard dismiss (Escape) and outside click detection.
- Disabled hiding the last remaining primary column in both UI and state handler.
- Added Reset sorting button when table is sorted and Reset all button when sorting or visibility is modified from defaults.
- Updated loading and empty states to span dynamically calculated visible column count.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Primary columns cannot be completely hidden by user controls.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added 5 tests in DataGrid.test.jsx covering column visibility toggles, primary column protection, reset buttons, empty row colspan, and loading row column matching. Verified all 14 tests pass.
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- Added focused component tests for row interaction with keyboard navigation (Enter/Space) and modifier key suppression.
- Tested custom sort comparator and accessor behavior for nested objects.
- Tested empty state recovery actions and toolbar configuration switches.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Nested interactive buttons in rows should not trigger whole-row click events.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added 4 tests in DataGrid.test.jsx covering pointer/keyboard activation, modifier suppression, custom accessors, and recovery actions. All 18 tests pass cleanly.
- Root cause (bugfix only): n/a




