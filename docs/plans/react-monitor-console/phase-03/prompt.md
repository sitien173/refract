## Original User Request

Execute the `react-monitor-console` folder plan. Complete only Phase 3.

## Phase

Deliver four live read-only monitor views in Flowforge style.

## Tasks

- task-1: Build shared table, status, panel, and empty-state components.
- task-2: Build the aggregating Overview view.
- task-3: Build Projects and Targets dense-table views.
- task-4: Build Profiles and wire hash-based navigation.

## Context

Reuse the existing typed hooks in `web/src/lib/queries.ts`. Do not duplicate
fetching or add backend routes. The backend serves only `/dashboard` and
`/dashboard/`, without an SPA fallback. Use React Router v7 `HashRouter`.
Application routes are `/`, `/projects`, `/targets`, and `/profiles`, producing
production URLs such as `/dashboard#/projects`.

Use `Routes`, `Route`, `Navigate`, and `NavLink`. The root link must use `end`
for exact active matching. Replace the brand anchor with router navigation.
Keep Jobs visible but disabled and labeled unavailable until Phase 4. Do not
create a Jobs view in this phase. Unknown hash routes return to Overview.

Shared components:

- `DataTable`: semantic table markup, horizontal overflow, 44px header, 56px
  rows, subdued dividers, neutral hover, and visible keyboard focus.
- `StatusBadge`: Flowforge token color plus local Lucide icon plus visible
  label. Support all job states and target health states needed by Overview.
- `EmptyState`: declarative sentence-case copy.
- `Panel`: neutral bordered surface with Title Case heading and optional
  compact supporting content. No decorative shadow.

Overview aggregates existing hooks in one page:

- Worker, active-job, and queued-job status tiles.
- At most five recent jobs from `useAllJobs`.
- Target-health summary.
- Project summary.
- Default and available profile summary.

Render available or cached data even when another query fails. A panel may show
an inline error alongside stale data. Never replace the entire page because one
query failed. Loading and empty states must be explicit.

Projects shows alias, root, head commit, clean or dirty status, and created
time. Targets shows ID, model, capabilities, active versus capacity, health,
and circuit state. A non-empty circuit timestamp is a labeled warning.
Unhealthy targets are labeled degraded. Profiles identifies the default and
lists all available profiles.

Follow Flowforge production rules:

- Use existing CSS variables only. No raw palette values.
- Use flat canvas and neutral panels.
- Table headers are 44px. Rows are 56px.
- Status uses color, icon, and label.
- Use local SVGs only.
- Use Title Case for page and panel headings.
- Use declarative sentence case for empty and error copy.
- Preserve light and dark token parity.

## Files

- `web/src/App.tsx`
- `web/src/App.test.tsx`
- `web/src/components/AppShell.tsx`
- `web/src/components/Sidebar.tsx`
- `web/src/components/DataTable.tsx`
- `web/src/components/StatusBadge.tsx`
- `web/src/components/EmptyState.tsx`
- `web/src/components/Panel.tsx`
- `web/src/components/*.test.tsx`
- `web/src/views/Overview.tsx`
- `web/src/views/Projects.tsx`
- `web/src/views/Targets.tsx`
- `web/src/views/Profiles.tsx`
- `web/src/views/*.test.tsx`
- `web/src/styles/app.module.css`
- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-03/notes.md`
- `docs/plans/react-monitor-console/phase-03/journal.md`

## Done When

- Overview renders all five live summary areas.
- Projects, Targets, and Profiles render live hook data.
- Hash routes render directly without backend fallback changes.
- Sidebar active state follows the current route.
- Jobs remains disabled until Phase 4.
- Tables use semantic markup and 44px by 56px geometry.
- Status always includes icon and label.
- Circuit-open and unhealthy targets are distinctly labeled.
- Loading, empty, stale, and partial-error states remain usable.
- No backend Python or data-layer changes occur.
- No raw colors, remote assets, or application timers are added.
- `npm --prefix web run build`
- `npm --prefix web test -- --run`

## Rules

Follow the supplied worker contract. Use test-first development. Stay within
the declared file set. Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
