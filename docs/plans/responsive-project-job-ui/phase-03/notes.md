<!-- ccg-shared-version: 10.4.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Extracted reusable `JobDetails.jsx` component presenting allowlisted execution trace, configuration revision, plan metadata, candidate targets, results, and errors.
- Strictly excluded sensitive fields (such as `system_prompt`, `secrets`, `args`, and `secret_instruction`) from display and execution-plan rendering.
- Provided accessible focus target on the job title heading via `tabIndex={-1}` and forwarded `headingRef`.
- Handled empty execution plans and missing revisions with clear fallback badges and labels.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Allowlisted display prevents credential or sensitive prompt leakage while providing comprehensive job execution visibility.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added `web/src/components/JobDetails.test.jsx` covering metadata, redaction, empty plan, results, polling toggles, and heading focus. All 9 tests pass.
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Added project-scoped route `/dashboard/projects/:projectId/jobs/:jobId` in `App.jsx`.
- In `ProjectDetail.jsx`, full job details fetch only after selecting a job (`selectedJobId`).
- Verified `job.project_id === projectId`; jobs belonging to another project render an error alert state.
- Integrated `usePolling` with `isTerminal` so job polling halts for all terminal states (`succeeded`, `failed`, `cancelled`, `interrupted`).
- On background refresh failures, preserved existing successful job details while displaying a non-blocking refresh warning.
- Focused the detail heading upon selection and returned keyboard focus to the originating job link upon navigating back.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Project context provides the canonical inspection environment for jobs.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added unit tests in `web/src/screens/ProjectDetail.test.jsx` verifying lazy job fetching, cross-project error handling, polling cutoff, and focus management. All 20 tests pass.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Added search, state filtering, and workflow filtering to the Jobs tab in `ProjectDetail.jsx`.
- Rendered genuine job links with standard `href` paths and keyboard navigation support.
- Included Clear filters button when search or filter values are active.
- Configured column definitions matching design specifications with priority and sort accessors.
- Stopped project jobs table list polling when all displayed jobs reach terminal status.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Search and filtering remain client-side for fast interactive response without server query overhead.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified search, state filter, and clear filter interactions in `ProjectDetail.test.jsx`. All 20 tests pass.
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- Removed `Jobs` from primary navigation in `Sidebar.jsx`.
- Kept `Projects` marked active in primary navigation for all project-scoped job routes.
- Bridged legacy `/dashboard/jobs` and `/dashboard/jobs/:jobId` routes to project-scoped equivalents in `JobDetail.jsx` and `App.jsx`.
- Updated integrated flows in `dashboard-flow.test.jsx` to test project-scoped navigation and legacy route compatibility.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Backward compatibility for existing bookmarks and URLs is maintained without keeping a redundant top-level navigation item.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Ran `npm --prefix web test -- src/components/JobDetails.test.jsx src/App.test.jsx src/screens/ProjectDetail.test.jsx src/screens/Jobs.test.jsx src/integration/dashboard-flow.test.jsx` (5 suites, 45 tests passing), full suite `npm --prefix web test` (16 suites, 113 tests passing), and `npm --prefix web run build`.
- Root cause (bugfix only): n/a

## Task 5

### Decisions made
- Replaced browser history entry via `replace: true` (and `history.replaceState`) during legacy `/dashboard/jobs/:jobId` resolution into `/dashboard/projects/:projectId/jobs/:jobId`, preventing circular Back button loops.
- Added `activeRouteRef` in `ProjectDetail.jsx` tracking `{ projectId, selectedJobId }` to verify current route context before committing async job fetch or polling state updates.
- Invalidated in-flight job requests on unmount or when `projectId` or `selectedJobId` change, discarding stale responses and preventing stale state overwrites.
- Cleared `selectedJobId`, `fullJob`, `jobFetchError`, and `jobRefreshError` whenever `projectId` changes.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Replacing history entry ensures browser Back navigates directly to the previous user destination instead of triggering repeated legacy resolution.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added regression tests in `dashboard-flow.test.jsx` checking `replaceState` on legacy resolution, and in `ProjectDetail.test.jsx` verifying job state clearing on `projectId` change, discarded in-flight fetches on route change, and discarded in-flight polling updates on navigation away. Ran focused suite (5 suites, 48 tests passing), full suite (16 suites, 116 tests passing), and `npm --prefix web run build`.
- Root cause (bugfix only): Legacy `/dashboard/jobs/:jobId` resolution previously pushed a new history entry instead of replacing it, causing Back loops; and `ProjectDetail.jsx` did not check route context identity before committing in-flight job responses.


