## User Request
Remove parallel readers and job dependencies from Refract. Phases 2 and 3 removed them from the server API. This phase removes the matching UI from the React dashboard.

## Phase
The dashboard shows no reader or dependency UI and its packaged build matches source.

## Tasks
- task-1: Remove `depends_on`, `waiting_on`, and `waiting_reason` columns, fields, sort accessors, and query handling from `server/web/src/screens/Jobs.jsx`, `screens/ProjectDetail.jsx`, `components/JobDetails.jsx`, and `hooks/useDashboardQuery.js` if it has any.
- task-2: Remove the `max_project_readers` reader-capacity form, its settings PUT call in `api.js`, and the `knownDaemonKeys` entry in `screens/RuntimeSettings.jsx`. The server no longer has `PUT /dashboard/api/settings`; `GET` settings stays.
- task-3: Update the listed tests to the reduced fields and settings. Delete only reader and dependency assertions; keep every other assertion in mixed-purpose tests. Earlier phases failed review for deleting mixed-purpose coverage. Then run `npm run build` in `server/web` to regenerate `server/src/refract/dashboard_static`.

## Context
- Design: docs/plans/remove-parallel-readers-dependencies/DESIGN.md. Plan: PLAN.md Phase 4.
- Files with current residue: api.js, api.test.js, App.test.jsx, components/JobDetails.jsx, components/JobDetails.test.jsx, screens/Jobs.jsx, screens/Jobs.test.jsx, screens/ProjectDetail.jsx, screens/ProjectDetail.test.jsx, screens/RuntimeSettings.jsx.
- Baseline: vitest 205 tests, 0 failed in three consecutive runs. Under heavy host load a few tests have flaked; Phase 1 fixed known causes. If a test fails intermittently, find the cause instead of adding retries or timeouts.
- Tests that type into dialogs first wait for `expect(dialog).toContainElement(document.activeElement)`; keep that pattern.

## Files
- Modify: server/web/src/{api.js,api.test.js,App.test.jsx}
- Modify: server/web/src/components/{JobDetails.jsx,JobDetails.test.jsx}
- Modify: server/web/src/hooks/useDashboardQuery.js
- Modify: server/web/src/screens/{Jobs.jsx,Jobs.test.jsx,ProjectDetail.jsx,ProjectDetail.test.jsx,RuntimeSettings.jsx}
- Regenerate only via `npm run build`: server/src/refract/dashboard_static/**
- Append only: docs/plans/remove-parallel-readers-dependencies/phase-04/notes.md and journal.md

## Done When
- `rg -n 'depends_on|waiting_on|waiting_reason|max_project_readers|access_mode|cancelled_dependents' server/web/src` returns no matches.
- `cd /home/ngosi/projects/refract/server/web && npx vitest run` passes three consecutive runs.
- `cd /home/ngosi/projects/refract/server/web && npm run build` succeeds and `server/src/refract/dashboard_static` contains no match for `max_project_readers` or `waiting_reason`.
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest tests/test_dashboard.py -q` passes.
- `cd /home/ngosi/projects/refract && git diff --check` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Do not hand-edit dashboard_static. Do not touch server Python or plugin.
- No Git writes. Do not read or edit secrets, `~/.refract`, the live daemon, or its database. Do not edit other files under `docs/plans/`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
