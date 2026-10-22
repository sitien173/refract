<!-- refract-shared-version: 1.2.0 -->

# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Removed access_mode, depends_on, waiting_on, and waiting_reason columns.
- Removed fields from Jobs.jsx and ProjectDetail.jsx.
- Removed admission mode, dependencies, waiting rows from JobDetails.jsx.
- No changes needed in useDashboardQuery.js.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Checked fields in web components.
- Tests updated to match reduced field set.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Removed max_project_readers capacity form from RuntimeSettings.jsx.
- Removed updateMaxProjectReaders API helper from api.js.
- Removed max_project_readers from knownDaemonKeys in RuntimeSettings.jsx.
- Removed project_readers restart-required setting row.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Removed PUT settings call and form.
- Checked knownDaemonKeys set without max_project_readers.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Updated App.test.jsx, api.test.js, JobDetails.test.jsx.
- Updated Jobs.test.jsx and ProjectDetail.test.jsx.
- Preserved non-reader and non-dependency test coverage.
- Rebuilt dashboard static assets with npm run build.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: npx vitest run passed 202 tests.
- Re-run three consecutive times passed.
- npm run build regenerated dashboard_static assets cleanly.
- pytest tests/test_dashboard.py passed 45 tests.
- Root cause (bugfix only): none
