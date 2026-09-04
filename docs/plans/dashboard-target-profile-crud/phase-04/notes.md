<!-- ccg-shared-version: 10.2.0 -->

# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Implemented mutateWithCsrf helper in web/src/api.js wrapping mutations with loopback verification, Cache-Control: no-store, If-Match revision header, and CSRF token handling.
- Added target configuration API methods: getConfigurationTargets, getConfigurationTarget, createConfigurationTarget, updateConfigurationTarget, and deleteConfigurationTarget.
- On 403 authorization failures with missing or invalid CSRF tokens, cleared cached token and requested fresh bootstrap token before retrying once.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Server requires exact revision matches on mutation endpoints via If-Match.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: npm --prefix web test -- --run src/screens/Targets.test.jsx failed with missing API exports, then passed once API helpers were implemented.

## Task 2

### Decisions made
- Created web/src/components/ConfigurationMutationDialog.jsx supporting both unreferenced confirmation checkboxes and structured blocking references display on 409 responses.
- Created web/src/components/TargetEditor.jsx exposing all 10 target fields: id, backend, model, backend_profile, reasoning, system_prompt, isolated, read_only, max_concurrency, and args.
- Added ordered repeatable argument controls with Add, Remove, Move Up, and Move Down actions without shell splitting or normalization.
- Protected dirty drafts against background query re-renders using isDirtyRef.
- Added save status indicator with accessible aria-live announcements covering saving, reloading, active, validation, conflict, and error states.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Target identifier is immutable in edit mode and mutable only during create mode.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: TargetEditor tests verified draft retention, argument reordering, and conflict notification.

## Task 3

### Decisions made
- Integrated target editor and mutation dialog modals into web/src/screens/Targets.jsx.
- Added "Create target" button to header actions and "Edit target" / "Delete target" buttons to docked Inspector.
- Preserved existing five-second health polling, health pill status markers, search filtering, and docked inspector details.
- Ensured background polling refreshes runtime status and configuration health without overwriting active editor drafts.
- Added FlowForge CSS styles in web/src/styles/app.css for grid layouts, argument control buttons, status banners, and reference tables.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Target system prompt and argument details remain inside the protected editor and never render in the public targets table.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Targets.test.jsx verified runtime health preservation, dirty draft retention during background polling, and redacted system prompts.

## Task 4

### Decisions made
- Added comprehensive unit tests in web/src/screens/Targets.test.jsx covering create mode, edit mode with locked identifier, dirty draft preservation during polling, revision conflict handling, unreferenced deletion confirmation, and referenced deletion blocking.
- Added end-to-end integration test in web/src/integration/dashboard-flow.test.jsx covering target creation with arguments, docked inspector navigation, deletion confirmation, sensitive data redaction, and CSRF token security.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Dialog elements require accessible ARIA modal attributes, distinct labels, and focus traps.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: npm --prefix web test -- --run src/screens/Targets.test.jsx src/integration/dashboard-flow.test.jsx passed all 13 tests across 2 test files.
