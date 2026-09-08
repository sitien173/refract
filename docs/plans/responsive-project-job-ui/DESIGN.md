# Responsive Project and Job Dashboard

## Purpose

Improve dashboard usability across laptop and desktop screens. Keep the existing
native table architecture while adding sorting, responsive column visibility,
and bounded extension points. Make Projects the canonical place for job history
and full job details.

## Users

Platform engineers and local OpenMCP operators are the primary users.

## Scope

The redesign provides:

- Responsive behavior for every dashboard table.
- Client-side sorting for declared sortable columns.
- Responsive and user-controlled column visibility.
- Project-scoped job history and full job details.
- Project-scoped deep links for individual jobs.
- Consistent table toolbars, focus behavior, and empty states.
- Removal of Jobs from the global sidebar.
- Compatibility handling for existing job URLs.

## Information Architecture

```text
OpenMCP
├── Overview
├── Projects
│   └── Selected project
│       ├── Effective configuration
│       ├── Profile resolution
│       ├── Task guidance
│       └── Jobs
│           └── Selected job
├── Targets
├── Profiles
├── Runtime settings
└── Configuration health
```

Projects become the canonical entry for jobs. The Jobs tab remains part of the
project workspace. Selecting a job replaces the jobs list with a full-width job
detail mode while preserving project context.

The canonical job route is:

```text
/dashboard/projects/:projectId/jobs/:jobId
```

Existing `/dashboard/jobs` and `/dashboard/jobs/:jobId` routes remain available
during migration. They resolve into the owning project rather than remaining a
separate navigation area.

## Table Direction

Keep and extend the existing `DataGrid` component. Do not add a table library.

A table library would provide state and row-model features, but would not solve
the current responsive layout constraints. The dashboard does not currently
require pagination, grouping, virtualization, pinning, or resizing. Retaining
native table markup limits migration cost and preserves existing styles, tests,
and accessibility behavior.

## DataGrid Capabilities

The shared `DataGrid` supports:

- Stable row identifiers.
- Client-side sorting.
- Controlled or uncontrolled sorting state.
- Responsive column priorities.
- User-controlled column visibility.
- Controlled or uncontrolled visibility state.
- Custom cell and header renderers.
- Optional row activation.
- Per-column minimum and preferred widths.
- Per-column wrapping behavior.
- Toolbar integration points.
- Existing loading and empty states.

Each sortable column declares its sorting behavior. Non-sortable columns remain
static. Equal values retain stable source ordering.

The component API preserves bounded extension points for later table features.
It does not implement unused features.

## Responsive Table Behavior

Laptop and desktop screens are the primary layouts.

Remove the global `980px` minimum table width. Each column declares its own
minimum and preferred width. Identifiers, statuses, dates, and short codes may
remain unwrapped. Descriptive values wrap when space is constrained.

Horizontal scrolling remains a fallback. It is not the default layout strategy.
Tables retain native tabular structure and do not become card collections.

Every table receives a common responsive wrapper. This includes direct table
markup outside `DataGrid`.

### Column Priorities

Columns use four visibility priorities:

| Priority | Behavior |
| --- | --- |
| Primary | Remains visible at supported laptop and desktop widths |
| Secondary | Hides after tertiary columns when width is constrained |
| Tertiary | Hides first when width is constrained |
| Optional | Hidden by default and available through visibility controls |

The Jobs table uses these defaults:

| Column | Priority |
| --- | --- |
| Job ID | Primary |
| State | Primary |
| Workflow | Primary |
| Target | Secondary |
| Profile | Secondary |
| Created | Tertiary |
| Configuration revision | Optional |

Responsive visibility and user visibility are separate inputs. A user may hide
an available column. Responsive rules may hide lower-priority columns when the
viewport cannot support them. Primary columns cannot all be hidden.

### Visibility Controls

Each applicable table provides a Columns menu containing labeled checkboxes.
The menu includes a reset action that restores screen defaults.

Visibility remains component state initially. Persistence across sessions is
excluded until required.

### Sorting

Sortable headers use buttons. Each button exposes the current state through
`aria-sort` on its column header. Activation cycles through ascending,
descending, and unsorted states.

The table toolbar provides a sorting reset when sorting is active. Sorting must
not mutate source data.

## Project Jobs Experience

The Project Jobs tab provides:

- Job search.
- State filtering.
- Workflow filtering.
- Sortable columns.
- Column visibility controls.
- Active-job polling.
- Loading, empty, stale, and error states.

Job identifiers remain genuine links. Whole-row activation may remain as a
convenience, but it does not replace the explicit link.

Selecting a job opens full-width detail mode inside the project workspace. The
Projects sidebar item remains active. Browser history records the selected job.
Browser Back returns to the jobs list with its current search, filters, sorting,
and visibility state.

## Full Job Details

Extract the presentational body of `JobDetail.jsx` into a reusable job-details
component. The component renders:

- Execution state and timestamps.
- Project, workflow, profile, target, and context key.
- Attempt count.
- Configuration revision.
- Selection policy.
- Candidate targets.
- Execution errors.
- Execution result output.
- Active polling state.

The containing route owns fetching, polling, navigation, and focus behavior. It
calls the existing `getJob(jobId)` endpoint only for the selected job. The jobs
list endpoint remains lightweight.

The existing execution-plan allowlist remains unchanged. The frontend must not
render fields excluded by the backend.

## Polling and Data Flow

The project jobs list polls while at least one listed job is non-terminal. It
stops when every listed job is terminal.

The selected job polls every five seconds while active. Polling stops when the
job reaches `succeeded`, `failed`, `cancelled`, or `interrupted`. Existing
visibility-change and unmount cleanup behavior remains intact.

A refresh failure preserves the last successful response and presents a
non-destructive warning. Polling updates must not move focus, close the detail
mode, reset table controls, or replace user selections.

The selected job must belong to the current project. A mismatched `project_id`
is handled as a not-found state.

## Layout and Visual Hierarchy

Remove permanently reserved inspector space from the project layout. A concise
inspector may remain for configuration metadata, but full job details use the
available content width.

Apply these interface rules consistently:

- Use existing design tokens and FlowForge styling.
- Preserve the 200px desktop sidebar.
- Prefer borders over decorative shadows.
- Keep page headings and actions visually distinct.
- Use consistent toolbar spacing and control heights.
- Align loading, empty, stale, and error states.
- Avoid decorative animation and gradients.
- Preserve current dark-mode token support.

A theme toggle is outside this scope.

## Accessibility

- Preserve native `table`, `thead`, `tbody`, `th`, and `td` elements.
- Associate headers and cells through valid table structure.
- Use `scope="col"` for column headers.
- Use genuine buttons for sortable headers.
- Use genuine links for job navigation.
- Keep visible `:focus-visible` styling.
- Support keyboard activation for optional row actions.
- Focus the job detail heading after navigation.
- Return focus to the originating job link when returning.
- Announce asynchronous warnings without replacing focused content.
- Keep status meaning available through text and shape, not color alone.

## Error Handling

| Condition | Dashboard response |
| --- | --- |
| Unknown project | Project not-found state |
| Unknown job | Job not-found state within project context |
| Project and job mismatch | Job not-found state |
| Initial jobs request failure | Error state with retry action |
| Jobs refresh failure | Preserve rows and show a warning |
| Initial job-detail failure | Detail error state with back action |
| Job-detail refresh failure | Preserve details and show a warning |
| Empty jobs list | Project-specific empty state |

Every recoverable error states what failed, what remains available, and how the
operator can retry.

## Migration

1. Extend `DataGrid` without changing existing screen behavior.
2. Apply responsive metadata and sorting declarations per screen.
3. Wrap direct table markup in the shared responsive structure.
4. Extract reusable job-detail presentation.
5. Add the project-scoped job route and detail mode.
6. Redirect or bridge existing job routes.
7. Remove Jobs from the sidebar.
8. Update integration coverage for the new canonical flow.

Existing API responses and persisted data require no migration.

## Testing

Component coverage includes:

- Stable ascending and descending sorting.
- Unsorted state restoration.
- `aria-sort` state.
- Default column visibility.
- User-controlled visibility.
- Responsive priority classes or attributes.
- Primary-column visibility constraints.
- Native table semantics.
- Keyboard sorting and row activation.
- Visibility reset behavior.

Project job coverage includes:

- Jobs is absent from the sidebar.
- The Project Jobs tab lists project jobs.
- Selecting a job renders complete details.
- Project context remains visible in detail mode.
- Browser navigation returns to the jobs list.
- Search, filters, sorting, and visibility remain intact.
- Active jobs poll and terminal jobs stop polling.
- Refresh failures preserve successful data.
- Project and job mismatches render not found.
- Sensitive execution-plan fields remain absent.
- Focus enters details and returns to the job link.

JSDOM does not verify visual overflow reliably. Responsive verification therefore
includes browser or manual viewport checks at representative laptop and desktop
widths.

## Success Criteria

- Supported laptop layouts avoid default horizontal scrolling where column
  priorities can preserve essential data.
- Every dashboard table has consistent responsive behavior.
- Operators can sort declared columns through pointer and keyboard input.
- Operators can control non-essential column visibility.
- Jobs no longer appear in global navigation.
- Operators reach complete job details from the owning project.
- Project context remains visible throughout job inspection.
- Legacy job links continue reaching the corresponding project job.
- Polling does not reset user controls or focused content.
- Existing sensitive-field boundaries remain intact.

## Non-goals

- Adding a third-party table library.
- Server-side sorting.
- Pagination.
- Virtualization.
- Column grouping.
- Column resizing.
- Column pinning.
- Persisted table preferences.
- Mobile card layouts.
- Theme switching.
- API or database schema changes.
- Immediate deletion of legacy job routes.
