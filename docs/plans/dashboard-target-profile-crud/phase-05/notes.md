<!-- ccg-shared-version: 10.2.0 -->

# Phase 5 — Decision Notes

## Task 1

### Decisions made
- Implemented global profile API methods in web/src/api.js: getConfigurationProfiles, getConfigurationProfile, createConfigurationProfile, updateConfigurationProfile, and deleteConfigurationProfile.
- Added project override API methods in web/src/api.js: getProjectProfileOverrides, getProjectProfileOverride, createProjectProfileOverride, updateProjectProfileOverride, and deleteProjectProfileOverride.
- Routed all profile mutations through mutateWithCsrf with loopback checks, no-store cache headers, CSRF auto-retry, and If-Match revisions.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Backend profile mutations require If-Match source revisions.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: npm --prefix web test -- --run src/screens/Profiles.test.jsx verified all profile API methods export and handle mutations.

## Task 2

### Decisions made
- Created reusable ProfileEditor component in web/src/components/ProfileEditor.jsx.
- Exposed parent profile selection and all four built-in workflows: consult, implement, review, and other.
- Built workflow controls with declaration toggle, ordered repeatable target list, max attempts, and timeout seconds.
- Kept undeclared workflows distinct from empty policies by sending null when undeclared.
- Frontend does not calculate inheritance or provenance; it displays backend-provided values.
- Supported keyboard interaction for target reordering controls.
- Mapped client-side validation errors directly to specific workflow cards.
- Protected dirty drafts against background query re-renders using isDirtyRef.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Sensitive target system prompts and arguments remain excluded from profile models and UI.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: ProfileEditor unit tests verified form validation, target ordering, draft retention, and conflict handling.

## Task 3

### Decisions made
- Integrated profile CRUD actions into web/src/screens/Profiles.jsx.
- Added Create profile button to page header and Edit profile / Delete profile buttons to docked Inspector.
- Preserved existing profile table format, global default indicator, and background health polling.
- Added unreferenced deletion confirmation dialog and referenced deletion blocking view.
- Added layout and editor styling in web/src/styles/app.css.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Deleting global default profile is blocked by referential integrity.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: DataGrid onRowClick opened Inspector to access edit and delete actions.

## Task 4

### Decisions made
- Added unit tests in web/src/screens/Profiles.test.jsx for create mode, edit mode, target reordering, workflow toggling, validation, draft preservation, conflict reload, and deletion.
- Added integration test in web/src/integration/dashboard-flow.test.jsx for end-to-end profile creation and deletion workflows with CSRF protection.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Background polling refreshes must never overwrite active drafts.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: npm --prefix web test -- --run src/screens/Profiles.test.jsx src/integration/dashboard-flow.test.jsx passed all 12 tests across both suites.
