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

## Correction Evidence

### 1. useAllJobs Initial Loading Semantics
- Fixed `useAllJobs` in `web/src/lib/queries.ts` so `isInitialLoading` is true only when no usable job rows exist (`!hasUsableRows`) and pending fan-outs remain (`numPendingNoData > 0`). Available rows are retained without full initial-loading replacement or premature empty state rendering while unresolved fan-outs remain.

### 2. TanStack Query Lifecycle Tests
- Added real TanStack Query lifecycle test suite to `web/src/lib/queries.test.tsx` without mocking hooks under test:
  - Proved detail and event requests start in parallel on selection.
  - Proved rerendering from job A to job B aborts both A signals.
  - Proved B resolving followed by late signal-ignoring A resolution retains B results only and keeps A/B keys isolated.
  - Proved unmounting while requests are pending aborts both signals and late ignored results after unmount cannot render or reopen anything.
  - Proved advancing fake timers after unmount causes no detail or event polls.

### 3. useAllJobs Provenance Tests
- Added provenance test suite to `web/src/lib/queries.test.tsx`:
  - Covered all initially failed fan-outs (`isInitialError=true`, `isInitialLoading=false`, `hasData=false`).
  - Covered partial rows (`hasPartialFailure=true`, keeps successful rows).
  - Covered partial empty (`hasPartialFailure=true`, `hasData=true`, `jobs=[]`).
  - Covered cached empty followed by refetch failure (`hasRefetchError=true`).
  - Covered cached projects refetch failure (`hasRefetchError=true`).
  - Covered one empty success while another is pending (`isInitialLoading=true`, no premature empty state).
  - Asserted no premature empty or full initial-loading replacement when usable data exists.

### 4. EventTimeline Coverage
- Extended `web/src/components/EventTimeline.test.tsx`:
  - Tested cached empty (`[]`) plus refetch error asserting both refresh warning and empty message.
  - Tested full-history replacement from `[event 1]` to `[event 1, event 2]` confirming exactly two rendered events and zero duplicate event elements.

### 5. Routing and URL Tests
- Extended `web/src/views/Jobs.test.tsx`:
  - Tested direct `#/jobs?selected=<id>`.
  - Tested missing and empty selection (`/jobs` and `/jobs?selected=`) keeping inspector closed.
  - Tested direct selected ID absent from aggregate mounting inspector and querying ID.
  - Tested encoded IDs containing `/`, `?`, and `&`.
  - Tested navigating from unselected to selected, then Browser Back returning to unselected URL and closing inspector.
  - Tested explicit close replacement preserving duplicate unrelated search parameters (`foo=1&foo=2`).

### 6. Inspector Commit Contract
- Removed `(data as any).result_commit` fallback from `web/src/components/Inspector.tsx`.
- Updated `Inspector.tsx` and `web/src/components/Inspector.test.tsx` to use valid `Job.result.commit` schema exclusively.

### 7. CSS Transition & Media Query Narrowing
- Narrowed `.inspector` CSS transition in `web/src/styles/app.module.css` to specific `opacity` and `transform` properties instead of `all`.
- Included `max-width: 100%` and `box-sizing: border-box` at the 768px media query breakpoint for `.inspector`.

### 8. Phase 4 Verification Gap Corrections
- Updated cached-empty refetch failure and cached-projects refetch failure tests in `web/src/lib/queries.test.tsx` to execute real refetches via hook query objects (`jobQueries[0].refetch()` and `projectsQuery.refetch()`) and await failed state. Confirmed cached data remains intact, `hasRefetchError === true`, `isInitialError === false`, `isInitialLoading === false`, and expected job list/empty array remains.
- Updated A-to-B isolation test in `web/src/lib/queries.test.tsx` using an explicit `QueryClient` and asserted all four query keys (`queryKeys.job('job-A')`, `queryKeys.jobEvents('job-A')`, `queryKeys.job('job-B')`, and `queryKeys.jobEvents('job-B')`) exist independently in the cache, with active B hook data remaining B after late A resolutions.
- Added App-level test in `web/src/App.test.tsx` that initializes real `HashRouter` at `#/jobs?selected=<encoded-id>`, confirming the Jobs page title remains sole `h1` and the Job Details `h2` opens for the decoded selection.
- Formatted abort detection condition in `web/src/lib/api.ts` into standard multi-line TypeScript style without modifying runtime behavior.
- All 16 web test files passed (144 tests), production build completed cleanly, and diff verified.

### 9. Phase 4 Review Finding Corrections (Job 2de94dbe-b12f-41da-8db0-6b71ba48e749)
- Added focused CSS contract test suite to `web/src/components/Inspector.test.tsx` verifying:
  - Phase 4 inspector styling uses Flowforge tokens for surface (`var(--color-surface)`), border (`var(--color-border-subdued)`), radius (`var(--radius-xs)`), elevation (`var(--elev-depth4)`), padding (`var(--space-lg)`), motion (`var(--motion-normal)`), and standard easing (`var(--ease-standard)`).
  - Reduced-motion `@media (prefers-reduced-motion: reduce)` override disables inspector transitions (`transition: none`).
  - Desktop list container `.jobsMainArea` keeps `min-width: 0`.
  - `@media (max-width: 768px)` breakpoint stacks `.inspector` with full width (`100%`) and `max-width: 100%`.
  - No fixed or absolute inspector positioning (`position: fixed` / `position: absolute`).
  - Zero raw palette values (hex codes, `rgb()`, or `hsl()`) in Phase 4 inspector styles, confirming dark parity relies strictly on CSS variables.
- Added keyboard-accessibility coverage in `web/src/views/Jobs.tsx` and `web/src/views/Jobs.test.tsx` for native `Open job <id>` button:
  - Enabled keyboard activation for Enter and Space using `onKeyDown` with `e.preventDefault()`, preserving native `<button type="button">` semantics and preventing duplicate selection in browser environments.
  - Verified `<tr>` elements contain no faux button roles or tabindices.
  - Verified row whitespace click activation and interactive-descendant suppression remain intact.
- Ran full web test suite (16 test files, 146 tests passing), production build (`npm --prefix web run build`), and `git diff --check`.
