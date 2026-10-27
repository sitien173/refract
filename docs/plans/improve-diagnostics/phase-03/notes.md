<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Decision Notes

## Task 1

### Decisions made
- Implemented `/dashboard/diagnostics` using FlowForge design tokens.
- Reused `PageHeader`, `DataGrid`, `StatusBadge`, and `Alert` primitives.
- Added `getDiagnostics` in `server/web/src/api.js`.
- Stripped empty query parameters to avoid backend errors.
- Discarded stale in-flight requests on filter or route changes.
- Formatted reports with ID, timestamp, category, and link.
- Explicitly labeled current execution state.
- Rendered untrusted report text inside plain text containers.
- Prevented HTML and script injection vulnerabilities.

### Spec deviations
- none

### Tradeoffs accepted
- Bounded pagination uses descending ID `before` cursors.
- Filter changes reset pagination to the first page.

### Assumptions
- Reports are client observations, not server-verified failures.
- Execution state remains independent from report presence.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `TypeError: api.getDiagnostics is not a function` in `src/api.test.js`. `Error: Failed to resolve import "./Diagnostics"` in `src/screens/Diagnostics.test.jsx`.
  - GREEN: `src/api.test.js` passed 5 tests. `src/screens/Diagnostics.test.jsx` passed 6 tests. `src/App.test.jsx` passed navigation test.

### Root cause (bugfix only)
- none

## Task 2

### Decisions made
- Added textual `.suspect-badge` with `.suspect-icon` non-color marker.
- Updated `Jobs.jsx`, `ProjectDetail.jsx`, and `JobDetails.jsx`.
- Fetched bounded diagnostic reports in `JobDetails.jsx`.
- Handled loading, empty, error, and stale states.
- Wired manual refresh to re-fetch terminal reports.
- Avoided automatic retry or reroute control.
- Rendered plain-text report summaries in dedicated panel.

### Spec deviations
- none

### Tradeoffs accepted
- Job diagnostic reports load on selection and manual refresh.
- Did not add continuous polling for diagnostic reports.

### Assumptions
- Backend returns `suspect` boolean and `diagnostic_count` integer fields.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `Unable to find an element with the text: Suspect` in `Jobs.test.jsx` and `ProjectDetail.test.jsx`.
  - GREEN: `Jobs.test.jsx` passed 16 tests. `ProjectDetail.test.jsx` passed 28 tests. `JobDetails.test.jsx` passed 30 tests. `dashboard-flow.test.jsx` passed 11 tests. Full frontend suite passed 263 tests across 22 files.

### Root cause (bugfix only)
- none

## Task 3

### Decisions made
- Documented `job_report_error` inputs and key reuse in `tool-contract.md`.
- Documented secret redaction and observation semantics.
- Documented retention following `Database.prune_history` on `updated_at`.
- Distinguished timeouts, questions, and partial paging from anomalies.
- Required awaiting complete terminal pagination before missing-output reports.
- Documented reporting anomalies before recovery in `review.md`.
- Preserved original IDs and prevented recursive reporting.
- Enforced that reporting failure never blocks safe reconciliation.
- Updated `server/README.md` to state nine MCP tools.
- Added `job_report_error` and `Diagnostic Reporting` in `server/README.md`.
- Preserved contract line count guards.

### Spec deviations
- none

### Tradeoffs accepted
- Kept tool contract additions concise for line guards.

### Assumptions
- Guidance applies to coordinator and external MCP clients.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `AssertionError: assert "job_report_error" in review` in `bash plugin/tests/run.sh`.
  - GREEN: `bash plugin/tests/run.sh` passed contract tests and manifest validation.

### Root cause (bugfix only)
- none

## Task 4

### Decisions made
- Ran consolidated checks across server, frontend, build, plugin, and git.
- Maintained clean separation of production artifacts.

### Spec deviations
- none

### Tradeoffs accepted
- Built frontend to an isolated temporary directory.
- Avoided touching tracked or untracked files in `server/web/dist`.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - `cd server && uv run --extra dev pytest -q`: 842 passed, 15 deselected in 167.57s.
  - `cd server/web && npm test`: 263 passed across 22 test files.
  - `build_dir=$(mktemp -d /tmp/refract-diagnostics-build.XXXXXX) && (cd server/web && npm run build -- --outDir "$build_dir")`: built in 2.59s.
  - `bash plugin/tests/run.sh`: session-start and contract tests passed; manifest valid.
  - `git diff --check`: passed with zero whitespace or line ending errors.

### Root cause (bugfix only)
- none

## Cycle 1 Fixes

### Decisions made
- Updated JobDetails to track previous job identity.
- Cleared reports when job identity changes.
- Prevented displaying job A reports under job B.
- Preserved reports on same job refresh failure.
- Rendered warning alert on same job refresh failure.
- Captured next_before cursor in JobDetails.
- Added explicit client observation label in report panel.
- Added bounded subset indicator in JobDetails.
- Added link to Diagnostics for remaining reports.
- Updated Diagnostics to track query identity.
- Cleared reports when query identity changes.
- Preserved reports on same query refresh failure.
- Added Enter and Space handlers on clear button.
- Removed orphaned getProjects import and mock.
- Reverted unrelated changes in Sidebar buttons.
- Specified summary and key bounds in documentation.
- Documented unique opaque per observation keys.
- Documented conflict behavior for duplicate report keys.
- Documented compact acknowledgement payload.
- Documented deduplication duration tied to event retention.
- Corrected README logging claim.
- Only correlation metadata is logged.
- Summaries and keys are never logged.
- Preserved tool contract line guard.

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
  - Cycle 1 behavioral RED:
    - `Diagnostics.test.jsx > supports keyboard activation on clear filters with Enter and Space`: FAILED with `Expected the element to have value: '' Received: 'proj-1'` at line 248.
    - `Diagnostics.test.jsx > clears old reports when query changes and does not attribute old reports or show warning on new query failure`: FAILED with `AssertionError: expected <code class="cell-code">102</code> to be null` at line 281.
    - `JobDetails.test.jsx > renders explicit client-observation label, bounded-subset indication, and link to diagnostics when next_before is present`: FAILED with `unable to find element with text /Client observations, not verified server failures/i` at line 729.
    - `JobDetails.test.jsx > clears old reports when job identity changes and does not attribute job A data to job B on slow or failed request`: FAILED with `AssertionError: expected <code class="cell-code">report-for-job-A</code> to be null` at line 779.
  - Task 1 behavioral RED retrospective:
    - `api.getDiagnostics`: Query parameter omission was validated against backend HTTP 400 rejection for empty strings; signal propagation was validated against aborted controller signals.
    - `Diagnostics.jsx`: Stale response rejection was validated by out-of-order promise resolution; XSS protection was validated by asserting injected HTML elements were null.
  - Cycle 1 GREEN:
    - `src/components/JobDetails.test.jsx`: 33 passed (33 tests).
    - `src/screens/Diagnostics.test.jsx`: 9 passed (9 tests).
    - `cd server/web && npm test`: 269 passed across 22 test files.
    - `cd server && uv run --extra dev pytest -q`: 842 passed, 15 deselected in 215.60s.
    - `build_dir=$(mktemp -d /tmp/refract-diagnostics-build.XXXXXX) && (cd server/web && npm run build -- --outDir "$build_dir")`: built in 1.76s.
    - `bash plugin/tests/run.sh`: passed session-start, contract tests, and manifest validation.
    - `git diff --check`: passed with zero whitespace or line ending errors.

### Root cause (bugfix only)
- In JobDetails, reports state was not cleared on job switch. Fixed by clearing reports when job ID changes.
- In Diagnostics, reports state was not cleared on filter change. Fixed by clearing reports when query key changes.
- In Diagnostics clear button, keyboard activation required onKeyDown. Fixed by handling Enter and Space keys.
- Orphaned getProjects was imported without usage. Fixed by removing import and mock.
- In Sidebar, buttons had unnecessary formatting and aria-current attributes. Fixed by reverting to original buttons.
- In README, summaries were claimed to be logged. Fixed to state only correlation metadata is logged.

## Cycle 2 Evidence Correction

### Decisions made
- Discarded getDiagnostics body to minimal callable stub in api.js.
- Kept api.test.js imports and tests runnable without compilation errors.
- Ran focused api.test.js to establish genuine behavioral RED evidence.
- Captured exact assertion failures for query building and signal propagation.
- Tested naive parameter mapper to capture empty parameter failure.
- Restored minimum getDiagnostics implementation body to GREEN.
- Distinguished cycle 1 screen regression from earlier unavailable RED.

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
  - Focused getDiagnostics stub behavioral RED:
    - Command: `cd server/web && npx vitest run src/api.test.js`
    - Stub 1: `return request('/dashboard/api/diagnostics')`
      - Failing assertion 1 (URL and query parameters):
        `FAIL src/api.test.js > dashboard API diagnostics client > queries diagnostics with optional bounded filters and cursor`
        `AssertionError: expected '/dashboard/api/diagnostics' to contain '/dashboard/api/diagnostics?'`
        `Expected: "/dashboard/api/diagnostics?"`
        `Received: "/dashboard/api/diagnostics"`
        at `src/api.test.js:88:23`.
      - Failing assertion 2 (Signal propagation):
        `FAIL src/api.test.js > dashboard API diagnostics client > propagates abort signal to fetch`
        `AssertionError: expected "spy" to be called with arguments: [ '/dashboard/api/diagnostics', ObjectContaining { "signal": AbortSignal {} } ]`
        `Received: [ '/dashboard/api/diagnostics', { "headers": { "Accept": "application/json" } } ]`
        at `src/api.test.js:116:23`.
      - Result: 2 failed | 3 passed (5 tests).
    - Stub 2 (naive parameter serialization without empty string omission):
      - Failing assertion 3 (Empty parameter omission):
        `FAIL src/api.test.js > dashboard API diagnostics client > omits empty filter parameters to prevent 400 bad request from server`
        `AssertionError: expected "spy" to be called with arguments: [ '/dashboard/api/diagnostics', Any<Object> ]`
        `Received: [ '/dashboard/api/diagnostics?projectId=&jobId=&category=', { "headers": { "Accept": "application/json" } } ]`
        at `src/api.test.js:104:23`.
      - Result: 2 failed | 3 passed (5 tests).
  - Screen behavioral RED distinction:
    - Original Task 1 screen RED evidence was unavailable and limited to initial import errors.
    - Cycle 1 established genuine failing behavioral RED regression on Diagnostics screen:
      `FAIL src/screens/Diagnostics.test.jsx > Diagnostics screen > clears old reports when query changes and does not attribute old reports or show warning on new query failure`
      `AssertionError: expected <code class="cell-code">102</code> to be null` at `src/screens/Diagnostics.test.jsx:281:39`.
  - Reimplemented GREEN:
    - Command: `cd server/web && npx vitest run src/api.test.js`
      Output: 5 passed (5 tests) in 74ms.
    - Command: `cd server/web && npx vitest run src/screens/Diagnostics.test.jsx`
      Output: 9 passed (9 tests) in 1477ms.
    - Command: `cd server/web && npm test`
      Output: 269 passed across 22 test files in 31.97s.
    - Command: `build_dir=$(mktemp -d /tmp/refract-diagnostics-build.XXXXXX) && (cd server/web && npm run build -- --outDir "$build_dir") && rm -rf "$build_dir"`
      Output: vite built in 2.81s.
    - Command: `bash plugin/tests/run.sh`
      Output: session-start tests passed, contract tests passed, manifest validation passed.
    - Command: `git diff --check`
      Output: clean, zero whitespace errors.

### Root cause (bugfix only)
- Minimal stub lacked query parameter assembly and signal forwarding.
- Reimplemented minimum body parsing options and propagating signal.

## Cycle 3 Navigation Fix

### Decisions made
- Dispatched `window.dispatchEvent(new PopStateEvent('popstate'))` in `App.jsx:navigate` after updating browser history and route state.
- Enabled mounted views like `Diagnostics` listening to `popstate` to reactively synchronize filters, pagination, and in-flight requests on SPA navigation.
- Preserved local filter editing and replaceState semantics by dispatching `popstate` only on explicit navigation actions.
- Preserved component tree stability and prevented spurious remounts or focus loss during typing.

### Spec deviations
- none

### Tradeoffs accepted
- Navigation dispatch triggers synchronous `popstate` handlers across mounted views matching browser back and forward button semantics.

### Assumptions
- Single-page application views synchronize URL query state via standard `popstate` event listeners.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - App-level behavioral RED:
    - Command: `cd server/web && npx vitest run src/App.test.jsx`
    - Failing assertion 1 (Filtered diagnostics -> sidebar navigation with delayed stale response):
      `FAIL src/App.test.jsx > dashboard shell > resets filtered diagnostics, handles delayed stale response, and resets pagination on sidebar navigation`
      `AssertionError: expected 'job-filtered' to be '' // Object.is equality`
      at `src/App.test.jsx:123:28`.
    - Failing assertion 2 (Repeat sidebar navigation after local filter edits):
      `FAIL src/App.test.jsx > dashboard shell > clears query and resets filters on repeat sidebar navigation after local filter edits`
      `AssertionError: expected 'job-edited' to be '' // Object.is equality`
      at `src/App.test.jsx:185:28`.
    - Result: 2 failed | 6 passed (8 tests).
  - Passing GREEN:
    - Command: `cd server/web && npx vitest run src/App.test.jsx`
      Output: 8 passed (8 tests) in 499ms.
    - Command: `cd server/web && npx vitest run src/screens/Diagnostics.test.jsx`
      Output: 9 passed (9 tests) in 821ms.
    - Command: `cd server/web && npx vitest run src/integration/dashboard-flow.test.jsx`
      Output: 11 passed (11 tests) in 2086ms.
    - Command: `cd server/web && npm test`
      Output: 271 passed across 22 test files in 19.57s.
    - Command: `build_dir=$(mktemp -d /tmp/refract-diagnostics-build.XXXXXX) && (cd server/web && npm run build -- --outDir "$build_dir") && rm -rf "$build_dir"`
      Output: built in 1.74s.
    - Command: `bash plugin/tests/run.sh`
      Output: session-start tests passed, contract tests passed, manifest validation passed.
    - Command: `git diff --check`
      Output: zero whitespace errors.

### Root cause (bugfix only)
- `App.jsx:navigate` called `window.history.pushState` or `replaceState` without dispatching a `popstate` event.
- Mounted views such as `Diagnostics` only synchronized filter state from URL on initial mount and `popstate` events.
- Navigating to `/dashboard/diagnostics` while mounted left filters, cursors, and in-flight requests unchanged.
- Fixed by dispatching `new PopStateEvent('popstate')` in `App.jsx:navigate`.
