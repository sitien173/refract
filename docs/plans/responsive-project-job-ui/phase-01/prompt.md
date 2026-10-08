## Original User Request
Complete `responsive-project-job-ui` using the confirmed design and phase plan.

## Phase
Deliver the tested responsive `DataGrid` foundation.

## Tasks
- task-1: Add backward-compatible sorting and visibility metadata.
- task-2: Implement stable controlled and uncontrolled table state.
- task-3: Add accessible controls and responsive column styling.
- task-4: Test sorting, visibility, activation, loading, and empty states.

## Context
The existing `DataGrid` is a basic native table. Preserve existing consumers. Remove the shared 980px minimum width. Follow `docs/plans/responsive-project-job-ui/DESIGN.md` and Phase 1 in `PLAN.md`.

## Files
- `web/src/components/DataGrid.jsx`
- `web/src/components/LoadingRows.jsx`
- `web/src/styles/app.css`
- `web/src/components/DataGrid.test.jsx`

## Done When
- Existing column definitions remain valid.
- Sortable columns cycle ascending, descending, and unsorted.
- Headers expose accurate `aria-sort` values.
- Equal values preserve source order.
- Visibility defaults follow metadata.
- Users cannot hide every primary column.
- Reset restores sorting and visibility defaults.
- Responsive classes hide lower-priority columns.
- Sorting does not mutate source rows.
- Loading and empty rows span visible columns.
- Native table semantics remain intact.
- `npm --prefix web test -- src/components/DataGrid.test.jsx`
- `npm --prefix web run build`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`. Add no dependencies or speculative table features.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
