# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Defined full TypeScript domain interfaces matching OpenMCP Python backend read models (DaemonStatus, Project, Job, JobEvent, Target, ProfilesResponse).

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Created `web/src/lib/types.ts` with strict TypeScript types and recursive `JsonObject`/`JsonValue` for events. Compiled cleanly with `tsc`.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Defined custom `ApiError` class extending `Error` to carry `endpoint` and HTTP `status` context on non-2xx responses.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `web/src/lib/api.test.ts` initially failed due to missing module `./api`. Implemented `web/src/lib/api.ts` with fetch wrappers for all 7 read endpoints forwarding AbortSignal and URL-encoding parameters; all 8 tests passed.
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Created centralized query key factory `queryKeys` and stable `QueryClient` configured with `refetchIntervalInBackground: false`, `refetchOnWindowFocus: 'always'`, `retry: false`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Created `web/src/lib/queries.test.tsx` which failed on missing `./queries`. Implemented `web/src/lib/queryClient.ts` and `web/src/lib/queries.ts` providing hooks (`useStatus`, `useProjects`, `useTargets`, `useProfiles`, `useJob`, `useJobEvents`, `useAllJobs`). All 6 query unit tests passed.
- Root cause (bugfix only): - none

## Task 4

### Decisions made
- Added Lucide icons (`circle-check.svg`, `triangle-alert.svg`, `wifi-off.svg`) and wired connection state pill and last-known metric counts / update timestamp retention in `TopBar`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `web/src/components/TopBar.test.tsx` failed before implementing connection state pills and testids. Implemented status derivation logic and count retention in `TopBar.tsx`, updated `App.tsx` with `QueryClientProvider`, and added CSS module classes in `app.module.css`. All 5 TopBar tests and full test suite (23 tests) passed.
- Root cause (bugfix only): - none

## Task 5

### Decisions made
- Extended `ApiError` constructor to accept optional cause parameter (`new ApiError(endpoint, statusOrCause, message)`). For network transport or JSON decode errors, `ApiError` captures `endpoint` and original `cause` without fabricating an HTTP status code.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Updated `request()` in `web/src/lib/api.ts` to wrap non-ApiError transport and decode exceptions. The existing API suite passed with 8 tests; polling coverage was deferred to Task 6.
- Root cause (bugfix only): Transport and JSON decode errors bypassed `ApiError` wrapping, losing endpoint context or risking fabricated status codes.

## Task 6

### Decisions made
- Added two API failure tests verifying endpoint context, undefined status, and identical original causes for transport and JSON decode failures.
- Added six behavioral TanStack Query tests using controlled timers and `focusManager` for polling, visibility, hook lifecycle, and failed-refetch retention.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Repaired the missing test work in `api.test.ts` and `queries.test.tsx`. The final fresh full web run reports 31 passing tests, up from the prior 23; the build also passes. No query production defect was exposed.
- Root cause (bugfix only): - none
