<!-- ccg-shared-version: 10.4.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Assigned responsive priorities across all dashboard screens:
  - Projects: alias (primary), health (primary), profile (secondary), activity (secondary), root (tertiary).
  - Targets: id (primary), health (primary), backend (secondary), model (secondary), active (secondary), max_concurrency (tertiary), isolated (optional), read_only (optional).
  - Profiles: name (primary), isDefault (primary), scope (secondary).
  - RuntimeSettings: setting (primary), value (primary), behavior (secondary), details (tertiary).
  - Jobs: id (primary), state (primary), workflow (primary), target_id (secondary), profile (secondary), created_at (tertiary), config_revision (optional).
  - ProjectDetail (effective config): workflow (primary), target (secondary), model (secondary), profile (tertiary), isolation (optional).
  - ProjectDetail (profile resolution): profile (primary), target (secondary), model (secondary), isolation (tertiary).
  - ProjectDetail (jobs): id (primary), state (primary), workflow (primary), target_id (secondary), profile (secondary), created_at (tertiary), config_revision (optional).
- Configured optional columns (such as config_revision, isolation, access) to default to hidden.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Core identifiers and statuses must remain visible without scrolling on standard desktop and laptop resolutions.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added assertions checking column priority class assignments across screen test files. All 5 test suites pass.
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Configured client-side sorting on all screen columns using explicit raw value sort accessors.
- Targets health sorts on normalized status order (`healthy`, `unhealthy`, `circuit-open`).
- Target concurrency and active jobs sort as numeric values rather than strings.
- Profile default status sorts boolean state directly.
- Runtime setting values and reload behaviors sort normalized strings.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- In-memory sorting provides immediate feedback without requiring extra backend query parameters.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added sort interaction assertions to screen tests (Projects, Targets, Profiles, Jobs, ProjectDetail). All tests pass.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Defined width and minWidth bounds on all screen DataGrid columns to avoid layout collapse.
- Marked path, model, description, and setting detail columns with `wrap: true` to prevent unbounded row widening.
- Kept badges, identifiers, status, and actions unwrapped and compact.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Text wrapping on long descriptive fields is preferable to horizontal truncation or excessive table stretching.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Verified layout stability and class rendering across screens and direct tables.
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- Wrapped remaining direct HTML tables (Profile editor targets override, ProjectDetail profile resolution, ProjectDetail fallback preview, ProjectDetail blocking references, ConfigurationMutationDialog references) in `.data-grid-container` scroll wrappers with `tabIndex={0}` and accessible region semantics.
- Added `scope="col"` to all direct table header elements (`th`) for accessibility.
- Added targeted CSS rules in `app.css` for direct tables inside modal dialogs and fallback panels.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Preserved direct table structures for small embedded modal matrices while providing consistent horizontal scrolling and accessible headers.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Ran `npm --prefix web test -- src/screens/Projects.test.jsx src/screens/Targets.test.jsx src/screens/Profiles.test.jsx src/screens/Jobs.test.jsx src/screens/ProjectDetail.test.jsx` (5 files, 48 tests passing) and `npm --prefix web run build` (vite build succeeds).
- Root cause (bugfix only): n/a

## Task 5

### Decisions made
- Derived deterministic sortable values from `row.rawTargets` in both `effectiveColumns` and `profileResolutionColumns` using `getEffectiveTargetsSortValue`.
- Maintained cell rendering from `row.targets` so presentation formatting remains intact while raw data drives table sorting.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Joining `row.rawTargets` in original array order preserves deterministic priority ordering when sorting.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added unit test for `getEffectiveTargetsSortValue` and component integration test in `ProjectDetail.test.jsx` verifying `rawTargets` dictates sort order independently of rendered targets text. All 17 tests in `ProjectDetail.test.jsx` and all 50 tests across the Phase 2 focused suite pass.
- Root cause (bugfix only): `Effective targets` sort accessors in `ProjectDetail.jsx` previously accessed `row.targets` directly instead of deriving from `row.rawTargets`.
