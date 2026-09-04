<!-- ccg-shared-version: 10.2.0 -->

# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Reconciled dense operational components around native tables, fixed columns, sticky headers, keyboard-reachable scroll regions, and stable loading rows.

### Spec deviations
- none

### Tradeoffs accepted
- Existing FlowForge component styles were extended rather than introducing another visual primitive.

### Assumptions
- CSS token dimensions are the source of truth for table headers and rows.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The partial frontend suite initially failed on isolated target status assertions; test isolation and existing state-marker coverage were reconciled, and the frontend suite passed.

## Task 2

### Decisions made
- Overview metrics link to filtered operational views; project hydration is capped at three concurrent workers.
- Runtime settings explicitly classify live, restart-required, and unclassified values.

### Spec deviations
- none

### Tradeoffs accepted
- Project summaries hydrate profile and activity data without polling project jobs on the overview cadence.

### Assumptions
- API payloads remain server-authoritative; the client only filters and renders them.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Overview, projects, targets, and runtime/configuration view tests passed with live/invalid and stale-data states covered.

## Task 3

### Decisions made
- Effective workflow rows are derived only from the server-provided `effective` mapping; declared/inherited data is used for provenance and display classification.
- Repository/global sources use distinct chips, with unknown values rendered neutrally.

### Spec deviations
- none

### Tradeoffs accepted
- Project detail keeps profile selection and workflow inspection local to the screen without adding a router dependency.

### Assumptions
- The backend has already resolved inheritance and source attribution.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Project detail tests passed for duplicate-free effective workflows, null parents, source mapping, docked inspection, and inherited classification.

## Task 4

### Decisions made
- Configuration-health views keep daemon availability and configuration validity separate and show last-known-good evidence during invalid states.
- Query failures preserve loaded data and show recovery guidance; polling timers are cleaned up and requests do not overlap.

### Spec deviations
- none

### Tradeoffs accepted
- Refresh controls remain explicit per view while operational polling is limited to overview, targets, configuration health, and project jobs.

### Assumptions
- The existing Phase 2 API error payloads provide safe messages and source paths.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Frontend suite passed with 18 tests; Python dashboard tests passed with 13 tests; full pytest passed with 310 passed and 3 deselected; production rebuild and wheel asset assertions passed.
