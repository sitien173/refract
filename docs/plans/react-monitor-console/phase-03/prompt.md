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

Place `HashRouter` outside `AppShell`, without a basename. Use `Routes`,
`Route`, `Navigate`, and `NavLink`. The root link must use `end` for exact
active matching. Replace the brand anchor with router navigation. Unknown hash
routes use `<Navigate to="/" replace />`.

Keep Jobs visible but disabled until Phase 4. Do not use a prevented `NavLink`
or anchor. Render a noninteractive element with `aria-disabled="true"`, visible
text `Jobs - Unavailable`, no `href`, and no tab stop. Do not create a Jobs
view. `#/jobs` follows the unknown-route redirect to Overview.

`AppShell` derives the route title and passes it to `TopBar`. Preserve one
page-level heading. View content starts below that heading.

Shared components:

- `DataTable<T>`: `caption`, `columns`, `rows`, and `getRowKey`. Columns own a
  Title Case header and cell renderer. Render `<table>`, `<caption>`,
  `<th scope="col">`, stable row keys, and a labelled, keyboard-focusable
  horizontal overflow region. Do not add tab stops to inert rows. Use
  `:focus-within` for row highlighting. Prevent unnecessary cell wrapping.
- `StatusBadge`: closed state union covering every `JobState`, `healthy`,
  `degraded`, `clean`, `dirty`, `circuit-open`, `circuit-closed`, and
  `circuit-unknown`. Map each state internally to a visible label, local Lucide
  icon, and token tone. Icons are `aria-hidden`.
- `EmptyState`: declarative sentence-case copy.
- `Panel`: neutral bordered surface with Title Case heading, children,
  optional supporting content, compact mode, and heading level. No decorative
  shadow.

Views own loading, error, stale, and empty decisions. `DataTable` does not.

Overview uses only `useStatus`, `useAllJobs`, `useTargets`, and `useProfiles`.
Reuse `useAllJobs().projectsQuery`; do not create another projects observer,
job-detail fetch, events fetch, or aggregate query. It renders:

- Worker, active-job, and queued-job status tiles.
- Exactly `jobs.slice(0, 5)` for recent jobs.
- Total, healthy, degraded, and open-circuit target counts.
- Total, clean, and dirty project counts.
- Default profile and every available profile.

Define view states consistently:

- Initial loading means no data exists and the query is loading.
- Initial error renders an inline error, never an empty state.
- A successful empty response renders `EmptyState`.
- A refetch error with cached data retains content and adds
  `Could not refresh. Showing last known data.`
- Partial `useAllJobs` failures retain successful jobs and show one
  partial-results warning.

Never replace the entire page because one query failed. Do not use `isStale`
for error messaging. Avoid live regions on polling badges. Reserve polite
announcements for high-level loading and error states.

Projects shows alias, root, head commit, clean or dirty status, and created
time. Use `<time dateTime>` for timestamps. Expose full commit values when
visually truncated.

Targets shows ID, model, capabilities, active versus capacity, health, and
circuit state. Derive circuit state in one shared presentation helper:

- A valid future timestamp is `Circuit Open`.
- An empty or expired timestamp is `Closed`.
- An invalid non-empty timestamp is `Circuit State Unknown`.

Health and circuit are independent. An unhealthy target always shows
`Degraded` plus its separate circuit badge. It may count in both Overview
totals. Reevaluate circuit expiry on normal query rerenders. Add no timer.

Profiles shows the default separately and lists every available profile. Mark
the matching list entry `Default`; do not remove it. Define empty-default and
empty-list behavior.

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
- `web/src/lib/presentation.ts`
- `web/src/lib/presentation.test.ts`
- `web/src/assets/icons/*.svg`
- `web/src/styles/app.module.css`
- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-03/notes.md`
- `docs/plans/react-monitor-console/phase-03/journal.md`

## Done When

- Overview renders all five live summary areas.
- Projects, Targets, and Profiles render live hook data.
- Hash routes render directly without backend fallback changes.
- Sidebar active state follows the current route.
- Brand navigation returns to Overview without reloading.
- Unknown routes redirect to Overview with replacement.
- Jobs remains a non-link disabled item until Phase 4.
- Tables use semantic markup and 44px by 56px geometry.
- Tables have captions, scoped headers, stable keys, and focusable overflow.
- Status always includes icon and label.
- All badge states have visible labels and hidden icons.
- Circuit-open, expired, invalid, and unhealthy states follow defined rules.
- Degraded health and Circuit Open may display simultaneously.
- Loading, empty, stale, and partial-error states remain usable.
- Overview shows at most five already-sorted jobs.
- Profiles retains and labels the default list entry.
- No backend Python or data-layer changes occur.
- No raw colors, remote assets, or application timers are added.
- `npm --prefix web run build`
- `npm --prefix web test -- --run`

Tests intentionally move shared `DataTable` and `StatusBadge` coverage forward
from Phase 4. Phase 4 extends these tests instead of recreating them. Cover
direct initial hashes, brand navigation, exact Overview active state, unknown
route replacement, disabled Jobs semantics, table captions and headers, every
badge state, all view data states, partial job failures, five-job limit,
simultaneous degraded and open-circuit badges, expired and invalid circuit
timestamps, and profile default membership. Verify geometry through CSS and
review, not jsdom layout calculations.

## Rules

Follow the supplied worker contract. Use test-first development. Stay within
the declared file set. Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
