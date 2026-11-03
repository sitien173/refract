<!-- refract-shared-version: 2.4.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Added `useProjects` and `useProject` wrapping `usePolling` in `hooks/usePolling.js` at 5s interval.
- Rendered Projects table at `#/projects` and detail at `#/projects/:id` in `ProjectsView.jsx`.
- Copied TDS `data-table`, `text-input`, `select`, and supporting `_shared` styles unmodified from TDS repository into `server/web/tds/Components/`.

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
  - RED: `cd server/web && npx vitest run src/views/ProjectsView.test.jsx` -> `FAIL src/views/ProjectsView.test.jsx (7 tests | 6 failed) Unable to find an element with the text: /loading projects/i`
  - GREEN: `cd server/web && npx vitest run src/views/ProjectsView.test.jsx` -> `✓ src/views/ProjectsView.test.jsx (7 tests) 232ms passed`
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Added `useTargets` and `useProfiles` wrapping `usePolling` in `hooks/usePolling.js` at 3s interval (matching overview interval from DESIGN.md).
- Implemented `TargetsView.jsx` with targets table (backend, model, isolation, read-only flag, active over max concurrency, breaker state, cooldown, probing, health) and profile routing matrix (profiles by workflow, ordered target chains, source labels).
- Wired `TargetsView` into `App.jsx` under `#/targets`.

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
  - RED: `cd server/web && npx vitest run src/views/TargetsView.test.jsx` -> `FAIL src/views/TargetsView.test.jsx (6 tests | 5 failed) Unable to find an element with the text: /loading targets and profiles/i`
  - GREEN: `cd server/web && npx vitest run src/views/TargetsView.test.jsx` -> `✓ src/views/TargetsView.test.jsx (6 tests) 244ms passed`
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Added `useDiagnostics` and `useSettings` wrapping `usePolling` in `hooks/usePolling.js` at 5s interval.
- Updated `usePolling` to detect fetcher changes across renders so updated query parameters trigger immediate refetches.
- Implemented `DiagnosticsView.jsx` with filters (project select, category select, job ID search input), before-cursor pagination, expandable expected and observed rows, and job links to `#/jobs/{job_id}`.
- Implemented `RuntimeView.jsx` displaying configuration health status (valid/invalid, latest error, last known good revision), daemon settings, and logging parameters from `fetchSettings`, exposing no secret values.
- Replaced all placeholder views in `App.jsx` with real read-only views (`ProjectsView`, `TargetsView`, `DiagnosticsView`, `RuntimeView`).

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
  - RED: `cd server/web && npx vitest run src/views/DiagnosticsView.test.jsx` -> `FAIL src/views/DiagnosticsView.test.jsx (8 tests | 7 failed) Unable to find an element with the text: /loading diagnostics/i`
  - GREEN: `cd server/web && npx vitest run src/views/DiagnosticsView.test.jsx` -> `✓ src/views/DiagnosticsView.test.jsx (8 tests) 569ms passed`
  - RED: `cd server/web && npx vitest run src/views/RuntimeView.test.jsx` -> `FAIL src/views/RuntimeView.test.jsx (6 tests | 5 failed) Unable to find an element with the text: /loading runtime settings/i`
  - GREEN: `cd server/web && npx vitest run src/views/RuntimeView.test.jsx` -> `✓ src/views/RuntimeView.test.jsx (6 tests) 276ms passed`
- Root cause (bugfix only): none

## FIX 1

### Decisions made
- Associated all DiagnosticsView state with a queryKey derived from active filters.
- Discard any polledData whose _queryKey does not match the active queryKey.
- Implemented a generationRef counter for handleLoadMore to discard in-flight responses when query key changes.
- Reset reports, cursor, and expanded rows atomically when queryKey changes.
- In usePolling, clear data and reset loading when fetcher identity changes.
- Added _queryKey tagging in useDiagnostics fetcher.
- Maintained paged cursor after polling by only updating nextBefore when extra pages have not been loaded.
- Deduplicated all reports by id when merging polled reports and loaded pages.
- Added aria-expanded and aria-controls to expand buttons with matching id on expanded row elements.
- Stripped trailing blank line in usePolling.js.
- Wrapped project select change in act(...) in App.test.jsx to eliminate act() warnings.

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
  - RED: `cd server/web && npx vitest run src/views/DiagnosticsView.test.jsx` -> `FAIL src/views/DiagnosticsView.test.jsx (12 tests | 3 failed) expect(element).toHaveAttribute("aria-expanded", "false"); expect(element).not.toBeInTheDocument(); expected "fetchDiagnostics" to be called with arguments: [ ObjectContaining { "before": "cursor-page-2" } ]`
  - GREEN: `cd server/web && npx vitest run src/views/DiagnosticsView.test.jsx` -> `✓ src/views/DiagnosticsView.test.jsx (12 tests) 1579ms passed`
- Root cause (bugfix only):
  - Defect 1: polledData remained in usePolling state across query changes and repopulated old reports; in-flight load-more had no generation or key check. Fixed by resetting state atomically on key change, discarding mismatched _queryKey and stale generations.
  - Defect 2: Polling effect unconditionally ran setNextBefore(polledData.next_before), overwriting paged cursor. Fixed by preserving nextBefore once hasPaged is true.
  - Defect 3: Appending and merging pages used simple array concatenation without deduplication by report id. Fixed by deduplicating by id.

## FIX 2

### Decisions made
- Added generationRef request counter to usePolling.
- Discarded in-flight responses if generation changed or unmounted.
- Bumped generation when enabled becomes false or on unmount.
- Cleared pending timer chains on overlapping refetches.
- Reset isLoadingMore to false when query key changes.
- Extended stale load-more test to assert new filter renders.
- Added test verifying isLoadingMore resets on filter change.

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
  - RED: `cd server/web && npx vitest run src/hooks/usePolling.test.jsx src/views/DiagnosticsView.test.jsx` -> `FAIL src/hooks/usePolling.test.jsx (3 failed: expected { version: 1 } to deeply equal { version: 2 }; expected 4 to be 3; expected { data: 'stale-data' } to be null), FAIL src/views/DiagnosticsView.test.jsx (1 failed: Unable to find an accessible element with the role "button" and name "/load more/i")`
  - GREEN: `cd server/web && npx vitest run src/hooks/usePolling.test.jsx src/views/DiagnosticsView.test.jsx` -> `✓ src/hooks/usePolling.test.jsx (11 tests) passed, ✓ src/views/DiagnosticsView.test.jsx (13 tests) passed; 24 tests passed across 2 test files`
  - Suite: `cd server/web && npm test` -> `✓ 94 tests passed across 14 test files`
- Root cause (bugfix only):
  - In usePolling, overlapping poll requests raced. Old requests overwrote state and spawned duplicate timers. Fixed with generation ref and timer invalidation.
  - In DiagnosticsView, stale load-more finally skipped resetting isLoadingMore. Fixed by resetting isLoadingMore on query key change.

## FIX 3

### Decisions made
- Bumped generationRef when visibilityState becomes hidden in usePolling.
- Discarded in-flight responses resolving after tab hides.
- Preserved immediate resume poll and completion on visible.
- Added tests for hide discard and resume completion.
- Added test for stale rejection after fetcher change.
- Added test for rapid refetch race conditions.

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
  - RED: `cd server/web && npx vitest run src/hooks/usePolling.test.jsx` -> `FAIL src/hooks/usePolling.test.jsx (2 failed: expected { data: 'hidden-data' } to be null; expected { initial: false } to be null)`
  - GREEN: `cd server/web && npx vitest run src/hooks/usePolling.test.jsx` -> `✓ src/hooks/usePolling.test.jsx (15 tests) passed`
  - Suite: `cd server/web && npm test` -> `✓ 98 tests passed across 14 test files`
- Root cause (bugfix only):
  - In usePolling, visibilitychange to hidden cleared timers only.
  - In-flight requests resolved afterwards and mutated state.
  - Incrementing generationRef on hidden discards in-flight responses.
