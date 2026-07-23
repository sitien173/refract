# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Created reusable StatusBadge mapping 13 status/health/circuit badge states with Flowforge color tokens and local SVG icons.
- Designed DataTable with keyboard-focusable horizontal scroll region (`tabIndex={0}`, `role="region"`) and 44px header / 56px row geometry.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- standard SVG icons from Lucide fit all required status badge roles.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - `src/lib/presentation.test.ts`: RED (missing module), GREEN (8 tests passed)
  - `src/components/StatusBadge.test.tsx`: RED (missing module), GREEN (15 tests passed)
  - `src/components/EmptyState.test.tsx`: RED (missing module), GREEN (1 test passed)
  - `src/components/Panel.test.tsx`: RED (missing module), GREEN (2 tests passed)
  - `src/components/DataTable.test.tsx`: RED (missing module), GREEN (1 test passed)

## Task 2

### Decisions made
- Built Overview view aggregating System Status, Recent Jobs (sliced to 5 max), Target Health, Projects Summary, and Profiles Summary.
- Reused `useAllJobs().projectsQuery` for project summaries to avoid redundant observers or backend calls.

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
  - `src/views/Overview.test.tsx`: RED (missing module), GREEN (3 tests passed)

## Task 3

### Decisions made
- Built Projects dense-table view displaying alias, root, head commit, clean/dirty status, and created timestamp.
- Built Targets dense-table view deriving circuit state independently from health state via `deriveCircuitState`.

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
  - `src/views/Projects.test.tsx`: RED (missing module), GREEN (5 tests passed)
  - `src/views/Targets.test.tsx`: RED (missing module), GREEN (5 tests passed)

## Task 4

### Decisions made
- Built Profiles view displaying default profile separately alongside all available profiles with default role indicator.
- Configured React Router v7 `HashRouter` without basename, with unknown route replacement (`path="*"` to `/`).
- Updated `Sidebar` with `NavLink` active states and noninteractive disabled `Jobs - Unavailable` item.
- Updated `AppShell` to derive route title from location pathname and pass to `TopBar`.

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
  - `src/views/Profiles.test.tsx`: RED (missing module), GREEN (5 tests passed)
  - `src/App.test.tsx`: GREEN (6 tests passed covering router, brand nav, disabled Jobs, unknown route redirect)
