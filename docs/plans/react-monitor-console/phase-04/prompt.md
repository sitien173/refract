## Original User Request

Execute the `react-monitor-console` folder plan. Complete only Phase 4.

## Phase

Deliver the live Jobs monitor and URL-driven debug inspector.

## Tasks

- task-1: Extend shared table behavior and enable Jobs navigation.
- task-2: Build the filtered cross-project Jobs view.
- task-3: Build the URL-driven job Inspector.
- task-4: Build the live EventTimeline and race coverage.

## Context

Reuse `useAllJobs`, `useJob`, and `useJobEvents` from
`web/src/lib/queries.ts`. The aggregation already fetches projects, fans out
per-project job queries, deduplicates by job ID, and sorts by `created_at`
descending. Do not add another projects observer, aggregate endpoint, local
polling timer, or backend route. Document the existing N+1 tradeoff in
`notes.md`.

Current React Router v7 guidance confirms `useSearchParams` updates the URL and
accepts navigation options. Use the existing `HashRouter`. The production URL
is `/dashboard#/jobs?selected=<encoded-id>`. Opening an inspector updates only
the `selected` parameter and preserves unrelated parameters. Closing removes
only `selected` using `{ replace: true }`. Directly loading a selected ID must
open the inspector even when the aggregated list has not loaded or does not
contain that job.

Current TanStack Query v5 guidance requires every job ID in its query key and
passing its `AbortSignal` through the fetch. Existing hooks already do both.
Selection rendering must use only the current ID's keyed query results. Closing
must disable detail and event queries. Switching from job A to job B must never
render A detail or events under B, including when A resolves last.

Add `/jobs` to `App.tsx`, title it `Jobs` in `AppShell`, and make the sidebar
Jobs item a normal `NavLink` labelled `Jobs`. Preserve all Phase 3 routes,
unknown-route replacement, exact Overview active state, and brand navigation.

`Jobs` owns these states:

- Initial loading has no cached aggregate data and announces
  `Loading jobs...`.
- Initial aggregate error renders `Failed to load jobs.`
- A successful empty aggregate renders `No jobs found.`
- A filter with no matches renders `No jobs match this filter.`
- A refetch error with cached data retains rows and adds
  `Could not refresh. Showing last known data.`
- Per-project failures retain successful rows and show one partial-results
  warning.

Provide a labelled native state filter with `All States` and every `JobState`:
Queued, Running, Succeeded, Failed, Cancelled, and Interrupted. Filtering is
client-side and preserves the aggregate ordering. The table includes Job ID,
Project, Workflow, Profile, State, and Created At. Use `<time dateTime>` and
`StatusBadge`. Expose the full job ID. Selecting any visible row sets
`selected`. Keep a real focusable control in every row so keyboard users can
open the inspector. If `DataTable` gains optional row activation, retain its
semantic `<table>`, caption, scoped headers, stable keys, focusable overflow,
and inert-row behavior.

The Jobs layout expands when no selection exists. With a selection, dock the
Inspector on the right inside the content layout. It is a non-modal
`<aside>` labelled by its Title Case heading. Do not add a focus trap or fixed
overlay. Use a neutral surface, left divider, 8px radius where exposed,
`--elev-depth4`, and a 250ms tokenized transition. Add a visible text close
button with an accessible name. On narrow screens, stack the inspector without
breaking content access.

The Inspector fetches the selected job directly. It renders:

- `Job Details` heading and close action.
- Full job ID, workflow, profile, project ID, attempts, and created/updated
  timestamps.
- `StatusBadge` for the exact job state.
- `Base Commit` and `Result Commit` values with a visible `Base to Result`
  relationship. Empty commits render `Not available`.
- Initial detail loading, initial error, cached-refetch warning, and data.

`EventTimeline` receives the selected ID and renders the existing
`useJobEvents` result. Polling remains the existing 2000ms hook interval and
must stop when the inspector closes. Render an ordered semantic list. Each
event shows its kind, `<time dateTime>`, and readable JSON data in a `<pre>`.
Preserve API order. Render `Loading events...`, `Failed to load events.`,
`No events recorded.`, and cached-refetch warning states consistently.

Status uses icon plus label. Icons remain local SVGs and `aria-hidden`. Use
existing Flowforge variables only. No raw colors, gradients, decorative
shadows, remote assets, or emoji. Buttons and labels use sentence case. Page,
panel, and inspector headings use Title Case. Keep one page-level heading from
the TopBar.

Extend tests rather than recreating Phase 3 coverage. Test:

- Direct `#/jobs` and `#/jobs?selected=<id>` routing.
- Jobs navigation active state and all prior navigation behavior.
- State filtering preserves descending order.
- Empty, filtered-empty, loading, initial-error, cached-error, and partial
  aggregate states.
- Row click and keyboard-accessible selection.
- Opening preserves unrelated search parameters.
- Closing removes only `selected`, uses replacement, and restores list width.
- Inspector detail fields, status, commit fallbacks, loading, initial error,
  and cached-refetch behavior.
- Timeline semantics, readable event data, empty/loading/error/cached states.
- Detail and events poll at 2000ms only while selected.
- Rapid A-to-B switching never shows A under B, even when A resolves last.
- Closing disables polling and late A responses cannot reopen content.
- Existing `DataTable` and `StatusBadge` contracts remain green.

## Files

- `web/src/App.tsx`
- `web/src/App.test.tsx`
- `web/src/components/AppShell.tsx`
- `web/src/components/Sidebar.tsx`
- `web/src/components/DataTable.tsx`
- `web/src/components/DataTable.test.tsx`
- `web/src/components/Inspector.tsx`
- `web/src/components/Inspector.test.tsx`
- `web/src/components/EventTimeline.tsx`
- `web/src/components/EventTimeline.test.tsx`
- `web/src/views/Jobs.tsx`
- `web/src/views/Jobs.test.tsx`
- `web/src/lib/queries.ts`
- `web/src/lib/queries.test.tsx`
- `web/src/styles/app.module.css`
- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-04/notes.md`
- `docs/plans/react-monitor-console/phase-04/journal.md`

## Done When

- Jobs renders the existing aggregate in descending order.
- Every state filter works without refetching.
- URL selection opens and closes the docked inspector.
- Direct selected URLs fetch the requested job.
- Switching or closing never exposes stale job data.
- Event polling runs only for an open inspector.
- Inspector and timeline cover every defined data state.
- Existing routes and shared component contracts remain intact.
- N+1 aggregation is reused and documented.
- No backend Python, API type, dependency, or unrelated changes occur.
- Generated output matches the production build.
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `git diff --check`

## Rules

Follow the supplied worker contract. Use test-first development. Stay within
the declared file set. Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
