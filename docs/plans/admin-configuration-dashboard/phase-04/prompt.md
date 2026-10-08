## Original User Request
Complete the OpenMCP admin configuration dashboard. Add configuration observability views using the existing React and FlowForge foundation.

## Phase
Add configuration observability views.

## Tasks
- task-1: Build reusable dense operational components.
- task-2: Add overview, projects, targets, and runtime views.
- task-3: Add effective profile resolution and source inspection.
- task-4: Add configuration-health and recovery states.

## Context
Phase 3 established the Vite React shell, client routing, dashboard API boundary, and packaged assets. Consume the existing Phase 2 API responses directly. The frontend must display server-resolved configuration without recomputing profile inheritance. Preserve previously loaded data when refreshes fail.

## Files
- `web/src/components/DataGrid.jsx`
- `web/src/components/PageHeader.jsx`
- `web/src/components/TabbedPanel.jsx`
- `web/src/components/Inspector.jsx`
- `web/src/components/LoadingRows.jsx`
- `web/src/screens/Overview.jsx`
- `web/src/screens/Projects.jsx`
- `web/src/screens/ProjectDetail.jsx`
- `web/src/screens/Targets.jsx`
- `web/src/screens/RuntimeSettings.jsx`
- `web/src/screens/ConfigHealth.jsx`
- `web/src/hooks/useDashboardQuery.js`
- `web/src/App.jsx`
- `web/src/api.js`
- `web/src/styles/app.css`
- `web/src/screens/Overview.test.jsx`
- `web/src/screens/ProjectDetail.test.jsx`
- `web/src/screens/ConfigHealth.test.jsx`
- `web/src/test/setup.js`
- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`
- `tests/test_dashboard.py`

## Done When
- Overview summary values link to filtered views.
- Project tables show alias, root, profile, activity, and health.
- Effective configuration distinguishes declarations and inheritance.
- Profile views show parent, workflows, targets, attempts, and timeouts.
- Targets show backend, model, isolation, concurrency, activity, and health.
- Runtime settings group live and restart-required values.
- Invalid configuration remains visible beside running daemon state.
- Tables use token-based 44px headers and 56px rows.
- Narrow layouts scroll tables without card conversion.
- Repository and global sources remain visibly distinct.
- Status always pairs color, icon, and label.
- Empty and error states provide specific recovery actions.
- Refresh failures preserve previously loaded data.
- Interactive rows support pointer and keyboard activation.
- The frontend never recomputes profile inheritance.
- Production assets are rebuilt and committed.
- `npm --prefix web run test`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py`
- `git diff --check`

## Consultation Findings
- Treat `effective` as each profile's workflow row set. Use `sources[workflow]` and `workflow in declared` only for server-provided attribution. Never concatenate `declared` and `inherited` rows.
- When `parent.value` is null, show `No parent` and suppress its source chip.
- Hydrate project summary rows with capped concurrency. Do not poll every project's jobs endpoint on the overview cadence.
- Carry configuration validity across catalog-derived screens. When invalid, preserve values and label them as last-known-good with the revision.
- Classify runtime settings through one explicit live/restart-required mapping. Show unknown keys under `Unclassified`. Render `logging.file === false` as `Console only`.
- Use token-based table heights, fixed table layout, explicit column widths, ellipsis with full-value titles, sticky `th` elements, and keyboard-reachable horizontal scroll regions.
- Preserve native table semantics. Use real links within interactive rows. Intercept only unmodified primary clicks.
- Add `popstate` handling, project-id route segments, and query-string filters without adding a router dependency.
- Query refresh failures must preserve current data. Avoid overlapping or out-of-order poll results and clean up timers.
- Map API source `project` to visible label `Repository`. Handle unknown source values neutrally.
- Distinguish healthy, circuit-open, and unhealthy targets. Status markers must have shape-distinct state classes, not color alone.
- Add tests for duplicate-free effective workflows, null parents, stale refresh data, route history and filters, last-known-good labelling, settings classification, table stability, source fallbacks, target states, and exact API response contracts.

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`. Reuse the existing API boundary and FlowForge tokens. Do not add a router dependency. Do not add CORS or credentials behavior. Keep one production Starlette process. Do not introduce new visual primitives when existing FlowForge patterns suffice.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
