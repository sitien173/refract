# Responsive Project and Job Dashboard Implementation Plan

## Source

Confirmed design: `docs/plans/responsive-project-job-ui/DESIGN.md`

## Scope

Extend the native dashboard table component with responsive visibility and
sorting. Apply the shared behavior across dashboard tables. Move full job
inspection into the owning project while preserving legacy job URLs.

No new table dependency, backend API, database migration, or theme control is
included.

### Phase 1: Extensible responsive DataGrid

**Task Guide Input:** Implement the shared React dashboard table foundation described in `docs/plans/responsive-project-job-ui/DESIGN.md`. Extend the existing native `DataGrid` with stable client-side sorting, accessible sortable headers, responsive column-priority metadata, controlled and uncontrolled column visibility, user visibility controls, reset behavior, per-column width and wrapping rules, and compatible loading, empty, and row-activation behavior. Update shared CSS to remove the global 980px minimum width and retain horizontal scrolling only as fallback. Add focused component tests. Do not add dependencies or implement pagination, virtualization, grouping, pinning, or resizing.

**Goal:** Provide one tested table component supporting the confirmed core behavior.

**Files:**
- Modify: `web/src/components/DataGrid.jsx`
- Modify: `web/src/components/LoadingRows.jsx`
- Modify: `web/src/styles/app.css`
- Create: `web/src/components/DataGrid.test.jsx`

**Tasks:**
1. Define backward-compatible column metadata for sorting, visibility priority, widths, and wrapping.
2. Implement stable sorting and controlled or uncontrolled state without mutating source rows.
3. Add accessible visibility controls, sorting reset, and valid native table semantics.
4. Add component coverage for sorting, visibility, row activation, loading, and empty states.

**Acceptance Criteria:**
- Existing column definitions remain valid.
- Declared sortable columns cycle ascending, descending, and unsorted.
- Sort headers expose accurate `aria-sort` values.
- Equal values preserve source ordering.
- Visibility defaults follow column metadata.
- Users cannot hide every primary column.
- Reset restores default sorting and visibility.
- Responsive classes hide lower-priority columns.
- Source rows remain unchanged after sorting.
- Loading and empty rows span visible columns.
- Native table elements remain intact.

**Reviewer Checklist:**
- Confirm state supports controlled and uncontrolled use.
- Confirm sorting handles empty values consistently.
- Confirm rendered cells match visible headers.
- Confirm keyboard and pointer activation do not conflict.
- Confirm the implementation excludes speculative features.
- Confirm CSS does not force every table to 980px.

**Verification Checks:**
- `npm --prefix web test -- src/components/DataGrid.test.jsx`
- `npm --prefix web run build`

**Commit:** `feat(dashboard): extend responsive data grid`

### Phase 2: Responsive tables across dashboard screens

**Task Guide Input:** Apply the Phase 1 `DataGrid` capabilities to every dashboard table. Add intentional sortable declarations, responsive column priorities, preferred widths, and wrapping rules for Projects, Targets, Profiles, Runtime Settings, Project configuration tables, and Jobs. Add consistent table toolbar behavior where applicable. Wrap remaining direct native tables in the shared responsive structure without changing their business behavior. Update existing screen tests for visible defaults and important sortable columns. Preserve laptop and desktop table layouts and keep horizontal scrolling as fallback. Do not convert tables into cards.

**Goal:** Make every dashboard table responsive and behaviorally consistent.

**Files:**
- Modify: `web/src/screens/Projects.jsx`
- Modify: `web/src/screens/Targets.jsx`
- Modify: `web/src/screens/Profiles.jsx`
- Modify: `web/src/screens/RuntimeSettings.jsx`
- Modify: `web/src/screens/Jobs.jsx`
- Modify: `web/src/screens/ProjectDetail.jsx`
- Modify: `web/src/components/ConfigurationMutationDialog.jsx`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/screens/Projects.test.jsx`
- Modify: `web/src/screens/Targets.test.jsx`
- Modify: `web/src/screens/Profiles.test.jsx`
- Modify: `web/src/screens/Jobs.test.jsx`
- Modify: `web/src/screens/ProjectDetail.test.jsx`

**Tasks:**
1. Classify each screen column as primary, secondary, tertiary, or optional.
2. Declare only meaningful sortable columns and comparison behavior.
3. Apply wrapping and width metadata to avoid default laptop overflow.
4. Give direct native tables the shared responsive wrapper and semantics.

**Acceptance Criteria:**
- Every dashboard table uses the shared responsive container behavior.
- Primary identifiers and statuses remain available at laptop widths.
- Lower-priority metadata hides before horizontal scrolling becomes necessary.
- Users can restore hidden columns through the Columns control.
- Descriptive content wraps while identifiers and statuses remain compact.
- Existing filters, editors, inspectors, and row actions retain behavior.
- Direct tables preserve valid headers and cell relationships.
- No table is converted into cards.

**Reviewer Checklist:**
- Inspect every `DataGrid` and direct table consumer.
- Confirm default priorities match each screen's operator tasks.
- Confirm sort accessors use raw values rather than rendered JSX.
- Confirm hidden columns do not remove essential actions.
- Confirm modal tables remain usable within viewport bounds.
- Confirm existing filtering and mutation flows remain unchanged.

**Verification Checks:**
- `npm --prefix web test -- src/screens/Projects.test.jsx src/screens/Targets.test.jsx src/screens/Profiles.test.jsx src/screens/Jobs.test.jsx src/screens/ProjectDetail.test.jsx`
- `npm --prefix web run build`

**Commit:** `feat(dashboard): apply responsive table behavior`

### Phase 3: Project-scoped full job details

**Task Guide Input:** Make Projects the canonical job navigation context. Remove Jobs from the sidebar. Add the route `/dashboard/projects/:projectId/jobs/:jobId`. In the Project Jobs tab, add job search, state filtering, workflow filtering, sorting, visibility controls, terminal-aware list polling, and genuine job links. Selecting a job must show the complete reusable job-detail presentation at full width within project context. Fetch full details only for the selected job, verify its `project_id`, preserve stale data during refresh failures, poll active jobs until terminal, focus the detail heading, and return focus to the originating job link. Preserve `/dashboard/jobs` and `/dashboard/jobs/:jobId` as compatibility routes that resolve into the owning project. Update unit and integration coverage, including execution-plan redaction assertions.

**Goal:** Provide complete job inspection within Projects without breaking old URLs.

**Files:**
- Modify: `web/src/App.jsx`
- Modify: `web/src/components/Sidebar.jsx`
- Modify: `web/src/screens/ProjectDetail.jsx`
- Modify: `web/src/screens/JobDetail.jsx`
- Create: `web/src/components/JobDetails.jsx`
- Create: `web/src/components/JobDetails.test.jsx`
- Modify: `web/src/screens/Jobs.jsx`
- Modify: `web/src/hooks/usePolling.js`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/App.test.jsx`
- Modify: `web/src/screens/ProjectDetail.test.jsx`
- Modify: `web/src/screens/Jobs.test.jsx`
- Modify: `web/src/integration/dashboard-flow.test.jsx`

**Tasks:**
1. Extract reusable job-detail presentation without changing exposed fields.
2. Add project-scoped routing, fetching, validation, polling, and focus behavior.
3. Add Jobs-tab search and filters while preserving table state across detail navigation.
4. Remove global Jobs navigation and bridge legacy job routes into Projects.

**Acceptance Criteria:**
- Jobs no longer appears in primary navigation.
- Projects remains active for project-scoped job routes.
- Job links use `/dashboard/projects/:projectId/jobs/:jobId`.
- Full status, revision, plan, targets, errors, and result output render inside Projects.
- Full details are fetched only after selecting a job.
- A job from another project renders a not-found state.
- Active job polling stops at every terminal state.
- Refresh failures preserve the last successful job details.
- Browser Back restores the Jobs table and its controls.
- Returning focus targets the originating job link.
- Legacy job URLs remain functional through compatibility routing.
- Sensitive execution-plan fields remain absent.

**Reviewer Checklist:**
- Confirm route parsing handles encoded project and job identifiers.
- Confirm legacy routes cannot loop or lose project ownership.
- Confirm selected job state clears when the project changes.
- Confirm polling cleanup and terminal-state behavior.
- Confirm stale refreshes do not reset focus or table state.
- Confirm reusable presentation receives allowlisted data only.
- Confirm navigation remains usable by keyboard and assistive technology.

**Verification Checks:**
- `npm --prefix web test -- src/components/JobDetails.test.jsx src/App.test.jsx src/screens/ProjectDetail.test.jsx src/screens/Jobs.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web test`
- `npm --prefix web run build`

**Commit:** `feat(dashboard): scope job details to projects`

## Completion Criteria

- All three phase verification sets pass freshly.
- The independent review confirms design compliance.
- No new frontend dependency appears in `web/package.json`.
- Legacy job URLs remain compatible.
- Every dashboard table has responsive behavior.
- `docs/plans/responsive-project-job-ui/CLOSEOUT.md` records final evidence.
