## Original User Request
Complete `responsive-project-job-ui` using the confirmed design and phase plan.

## Phase
Apply responsive table behavior across dashboard screens.

## Tasks
- task-1: Classify each screen column by responsive priority.
- task-2: Declare meaningful sorting using raw values.
- task-3: Apply width and wrapping metadata.
- task-4: Align remaining direct tables and screen tests.

## Context
Phase 1 delivered the shared `DataGrid`. Follow `docs/plans/responsive-project-job-ui/DESIGN.md` and Phase 2 in `PLAN.md`. Preserve business behavior, filters, editors, inspectors, and actions.

## Files
- `web/src/screens/Projects.jsx`
- `web/src/screens/Targets.jsx`
- `web/src/screens/Profiles.jsx`
- `web/src/screens/RuntimeSettings.jsx`
- `web/src/screens/Jobs.jsx`
- `web/src/screens/ProjectDetail.jsx`
- `web/src/components/ConfigurationMutationDialog.jsx`
- `web/src/styles/app.css`
- `web/src/screens/Projects.test.jsx`
- `web/src/screens/Targets.test.jsx`
- `web/src/screens/Profiles.test.jsx`
- `web/src/screens/Jobs.test.jsx`
- `web/src/screens/ProjectDetail.test.jsx`

## Done When
- Every dashboard table uses shared responsive container behavior.
- Primary identifiers and statuses remain available at laptop widths.
- Lower-priority metadata hides before fallback scrolling.
- Users can restore hidden columns through Columns controls.
- Descriptions wrap while identifiers and statuses remain compact.
- Existing filters, editors, inspectors, and row actions retain behavior.
- Direct tables preserve valid header and cell relationships.
- No table becomes cards.
- `npm --prefix web test -- src/screens/Projects.test.jsx src/screens/Targets.test.jsx src/screens/Profiles.test.jsx src/screens/Jobs.test.jsx src/screens/ProjectDetail.test.jsx`
- `npm --prefix web run build`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`. Add no dependencies.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
