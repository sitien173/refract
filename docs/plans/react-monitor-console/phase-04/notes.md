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

## Task 2

### Decisions made
- Implemented state filtering client-side preserving created_at descending order.
- Rendered project alias from projectsQuery.data with fallback to project_id.
- Handled all aggregate states: initial loading (Loading jobs...), initial error (Failed to load jobs.), empty aggregate (No jobs found.), filtered empty (No jobs match this filter.), cached-refetch error (Could not refresh. Showing last known data.), partial failure warning (Could not load jobs for all projects. Showing partial results.), and empty partial failure (No jobs found in available results.).
- Exposed full job ID with native button aria-label="Open job <id>" without adding role/tabindex to tr elements.

### Spec deviations
- none

### Tradeoffs accepted
- Documented N+1 aggregate tradeoff in useAllJobs (fans out per-project job queries client-side).

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - web/src/views/Jobs.test.tsx: Tested state filtering, aggregate loading/error/partial states, project alias display, row click selection, search parameter preservation, and focus restoration. Confirmed GREEN.

## Task 3

### Decisions made
- Created Inspector non-modal aside labelled by aria-labelledby="inspector-heading" with h2 Title Case "Job Details" and visible text close button.
- Rendered full job ID, workflow, profile, project ID, attempts, timestamps (<time dateTime>), StatusBadge, and commit relationship (Base to Result). Fallback to "Not available" for empty commits.
- Mounted EventTimeline inside Inspector unconditionally so detail and event queries start independently and in parallel.
- URL selection uses search parameter selected. Opening and switching use push navigation; closing uses replace navigation ({ replace: true }).

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
  - web/src/components/Inspector.test.tsx: Tested Title Case heading, close button, aria-labelledby, detail fields, status badge, commit fallbacks, loading, initial error, cached refetch, and independent timeline mounting. Confirmed GREEN.

## Task 4

### Decisions made
- Preserved existing EventTimeline polling and rendering logic for event list items, raw JSON data pre formatting, and array order preservation.
- Ensured switching selection or closing unmounts observers and aborts in-flight requests cleanly via AbortController signals without exposing errors to users.

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
  - web/src/views/Jobs.test.tsx: Tested A-to-B switching, history Back navigation, URL parameter preservation, focus restoration, and unmounting on close. Confirmed GREEN (16 test files, 124 tests passing).
