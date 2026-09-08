## Original User Request
Complete `responsive-project-job-ui` using the confirmed design and phase plan.

## Phase
Make Projects the canonical full job-detail context.

## Tasks
- task-1: Extract reusable allowlisted job-detail presentation.
- task-2: Add project-scoped routes, validation, polling, and focus.
- task-3: Add Jobs-tab search, filters, links, and state preservation.
- task-4: Remove sidebar Jobs and bridge legacy routes.

## Context
Phases 1 and 2 delivered responsive tables. Follow `docs/plans/responsive-project-job-ui/DESIGN.md` and Phase 3 in `PLAN.md`. Preserve legacy URLs and existing sensitive-field boundaries.

## Files
- `web/src/App.jsx`
- `web/src/components/Sidebar.jsx`
- `web/src/screens/ProjectDetail.jsx`
- `web/src/screens/JobDetail.jsx`
- `web/src/components/JobDetails.jsx`
- `web/src/components/JobDetails.test.jsx`
- `web/src/screens/Jobs.jsx`
- `web/src/hooks/usePolling.js`
- `web/src/styles/app.css`
- `web/src/App.test.jsx`
- `web/src/screens/ProjectDetail.test.jsx`
- `web/src/screens/Jobs.test.jsx`
- `web/src/integration/dashboard-flow.test.jsx`

## Done When
- Jobs disappears from primary navigation.
- Projects remains active for project-scoped job routes.
- Job links use `/dashboard/projects/:projectId/jobs/:jobId`.
- Full allowlisted job details render inside Projects.
- Full details fetch only after job selection.
- Cross-project jobs render not found.
- Polling stops for every terminal state.
- Refresh failures preserve successful details.
- Browser Back restores Jobs table controls.
- Focus enters details and returns to the originating link.
- Legacy job URLs resolve into owning projects.
- Sensitive execution-plan fields remain absent.
- `npm --prefix web test -- src/components/JobDetails.test.jsx src/App.test.jsx src/screens/ProjectDetail.test.jsx src/screens/Jobs.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web test`
- `npm --prefix web run build`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`. Add no dependencies. Preserve existing API contracts.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
