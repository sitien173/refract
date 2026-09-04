<!-- ccg-shared-version: 10.2.0 -->

# Phase 6 — Decision Notes

## Task 1

### Decisions made
- Reused ProfileEditor in web/src/screens/ProjectDetail.jsx.
- Added create override, edit override, and remove override actions.
- Enabled self-extension for project overrides in ProfileEditor.
- Handled missing project config files with empty revisions.
- Labeled removal button explicitly as Remove override.
- Protected dirty editor drafts against polling reloads.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Project overrides can self-extend same-named global profiles.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: web/src/screens/ProjectDetail.test.jsx verified override CRUD actions.

## Task 2

### Decisions made
- Rendered server-resolved global fallback policy in removal dialog.
- Added frontend unit tests for override workflows and conflicts.
- Added integration flow test for override lifecycle in dashboard-flow.
- Added backend tests in tests/test_dashboard.py for override aliases.
- Verified existing job execution plans remain preserved in runtime.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Removal previews use server-resolved global profiles.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: tests/test_runtime.py verified plan preservation.
- RED -> GREEN: web/src/screens/ProjectDetail.test.jsx passed with preview assertions.

## Task 3

### Decisions made
- Updated README.md configuration boundaries for editable targets and profiles.
- Documented loopback security, CSRF headers, and If-Match revisions.
- Documented deletion restrictions and registered-project reference limits.
- Clarified unregistered external workspaces cannot be scanned.
- Updated DESIGN.md to remove read-only constraints and align scopes.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Core daemon settings remain externally managed on disk.

### Follow-ups for human
- none

### Test evidence
- Verification checked documentation consistency across README and DESIGN.

## Task 4

### Decisions made
- Rebuilt frontend static assets bundle using Vite.
- Executed full backend test suite with pytest.
- Executed full frontend test suite with vitest.
- Verified packaging with uv build.
- Verified system configuration with openmcp doctor.
- Confirmed git diff formatting cleanliness.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Built web assets must be packaged in Python distribution.

### Follow-ups for human
- none

### Test evidence
- All backend and frontend test suites passed cleanly.
