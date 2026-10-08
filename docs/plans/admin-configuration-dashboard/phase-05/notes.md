<!-- ccg-shared-version: 10.2.0 -->

# Phase 5: Decision Notes

## Task 1

### Decisions made
- Implemented accessible portal modal with focus trapping.
- Added context instruction editor for workflows.
- Required explicit confirmation before submitting mutations.
- Used outlined red styling for destructive clear actions.
- Preserved drafts on HTTP 409 conflicts.

### Spec deviations
- none

### Tradeoffs accepted
- Mutation confirmation requires checking an explicit checkbox.
- Re-confirmation is required following conflict recovery.

### Assumptions
- Context instructions affect future jobs only.
- In-flight and terminal jobs remain unchanged.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added context instruction editor coverage.
- Confirmed mutation payloads transmit expected current values.
- Verified DELETE clear requires expected current values.

## Task 2

### Decisions made
- Created scoped Jobs and JobDetail screens.
- Rendered configuration revision SHA-256 or unavailable notice.
- Rendered only allow-listed execution plan fields.
- Hidden arguments and system prompts remain excluded.

### Spec deviations
- none

### Tradeoffs accepted
- Execution plan inspection relies on server redactions.

### Assumptions
- Backend plan redaction is authoritative.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added Jobs and JobDetail test suites.
- Verified allow-listed fields render without leakage.
- Verified missing revisions show unavailable states.

## Task 3

### Decisions made
- Implemented usePolling with five second intervals.
- Stopped polling when all displayed jobs are terminal.
- Paused polling while the document is hidden.
- Maintained persistent polite live region for status announcements.
- Reported conflict errors using assertive alerts.

### Spec deviations
- none

### Tradeoffs accepted
- Document visibility events trigger immediate refresh ticks.

### Assumptions
- Terminal states include succeeded, failed, cancelled, and interrupted.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added polling and conflict regression tests.
- Reconciled conflict retry to update expected values.
- Verified live region updates across mutations.

## Task 4

### Decisions made
- Documented dashboard loopback scope in README.
- Documented editable context instructions and read-only boundaries.
- Stated that remote administration is unsupported.
- Rebuilt production assets into python package.

### Spec deviations
- none

### Tradeoffs accepted
- README documentation maintains strict loopback positioning.

### Assumptions
- OpenMCP daemon binds only to local interfaces.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added documentation boundary tests in pytest.
- Verified wheel archive contains static dashboard assets.
- All 12 frontend test suites and 42 tests passed.
- Full pytest suite passed with 313 tests.

## Reconciliation — substantial partial working tree

### Decisions made
- Retained and reconciled the existing editor, modal, jobs, detail, polling, and integration work rather than duplicating the Phase 5 surfaces.
- Added exact backend contract coverage for the built-in workflow set and nested context-instruction response envelope.
- Documented the dashboard's loopback-only administration scope, editable context boundary, read-only file-managed configuration, and lack of remote administration support.

### Spec deviations
- none

### Tradeoffs accepted
- The online `npm --prefix web ci` invocation timed out while resolving the registry; the same lockfile installation completed successfully with `--offline`, followed by passing tests and build.

### Assumptions
- Existing Phase 2 API redaction and CSRF response contracts remain authoritative for the frontend.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added backend contract assertions and documentation boundary checks; frontend suite passed with 46 tests, focused Python suite passed with 36 tests, full pytest passed with 313 passed and 3 deselected, offline npm installation passed, Vite production rebuild passed, `uv build` and wheel asset checks passed, and `git diff --check` passed.

## Review Fix — Phase 5 findings

### Decisions made
- Added concurrent mutation regression to api.test.js.
- Confirmed concurrent mutations share single CSRF bootstrap.
- Exercised modal initial focus, tab trapping, and restoration.
- Added polling cleanup after unmount test.
- Added focused component tests in Modal.test.jsx.
- Added focused hook tests in usePolling.test.jsx.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added test suites for review findings.
- Total 15 test files and 56 tests passed.
- git diff check passed with zero whitespace errors.
