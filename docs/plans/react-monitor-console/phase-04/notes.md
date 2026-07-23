# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Handled abort error identity in api.ts by checking signal.aborted and err.name === 'AbortError', rethrowing original error.
- Extended DataTable with optional onRowClick that ignores interactive descendants without adding role/tabindex to tr elements.

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
  - src/lib/api.test.ts: Added test for rethrowing original abort error unchanged when request signal is aborted. Confirmed RED (wrapped in ApiError) -> GREEN.
  - src/components/DataTable.test.tsx: Added test for optional onRowClick firing on non-interactive cells and ignoring interactive buttons without tr role/tabindex. Confirmed RED -> GREEN.
  - src/App.test.tsx: Updated navigation tests for /jobs route and active sidebar NavLink. Confirmed GREEN.
