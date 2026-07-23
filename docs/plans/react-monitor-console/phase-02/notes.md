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
- Added comprehensive behavioral TanStack Query integration tests for 3000ms general status polling, 2000ms job/event polling, hidden window focus suppression via `focusManager`, immediate refetch on visibility restoration, unmount/disabled polling cessation, and cached data / dataUpdatedAt retention on background query failure.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `web/src/lib/api.test.ts` transport/decode error tests failed when raw errors were unhandled. Updated `request()` helper in `web/src/lib/api.ts` to wrap non-ApiError exceptions into `ApiError(endpoint, cause)`. All 10 API unit tests passed. Added 6 behavioral TanStack Query tests in `web/src/lib/queries.test.tsx`; all 31 tests passed cleanly.
- Root cause (bugfix only): Transport and JSON decode errors previously bypassed `ApiError` wrapping, losing `endpoint` context or risk fabricating status codes. Wrapped all non-`ApiError` exceptions caught during `fetch` or `res.json()` into `ApiError(endpoint, cause)`.

## Task 6

### Decisions made
- Added verification test suite in `web/src/lib/api.test.ts` verifying transport and JSON decode failures wrap into `ApiError` with endpoint context, undefined status (no fabrication), and original cause.
- Added verification behavioral test suite in `web/src/lib/queries.test.tsx` using `focusManager` and controlled timers verifying 3000ms status polling, 2000ms job/event polling, hidden window focus request suppression, immediate refetch on visibility restoration, unmount/disabled polling cessation, and cached data / dataUpdatedAt retention on failed refetch.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added test cases in `api.test.ts` and `queries.test.tsx`. Verified behavior against existing `web/src/lib/api.ts` and `web/src/lib/queries.ts` implementations (no production code defects exposed; production code untouched). Full test suite (31 tests) and build passed cleanly.
- Root cause (bugfix only): - none
