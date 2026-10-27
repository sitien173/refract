## User Request
Finish the approved diagnostics plan. Run long validation in the background. Implement Phase 3 only.

## Phase
Dashboard investigation and client adoption guidance.

## Tasks
1. Add genuine failing UI/API-client tests before production changes. Implement /dashboard/diagnostics, navigation, project/job/category filters, bounded next-page pagination, refresh, and job links using existing UI primitives.
2. Add visually separate textual suspect badges to standalone/project job lists and job details. Fetch bounded reports with loading, empty, error and stale-response handling. Manual refresh must discover new reports for terminal jobs in both navigation contexts.
3. Document reporting inputs, key reuse, privacy limitations, retention and client-observation semantics. Distinguish wait timeouts, pending questions, partial pagination and genuine anomalies. Await complete terminal pagination before missing-output reports. Require ERP only where the workflow requires it. Generic worker error text under succeeded is an output-report example. Report genuine anomalies before recovery; preserve original IDs. Reporting failure never causes recursive reporting or blocks safe reconciliation.
4. Verify UI integration, server, plugin and isolated production build. Record precise test evidence and full ERP.

## Context
Repository: /home/ngosi/.worktrees/refract/improve-diagnostic.
Read docs/plans/improve-diagnostics/{DESIGN,PLAN}.md; Phase 3 is authoritative.
Phases 1 and 2 are complete. No server implementation changes are authorized.
GET /dashboard/api/diagnostics accepts optional project_id, job_id, category, exclusive positive event-ID before, limit 1..100 default 50. Returns {reports,next_before} descending IDs. Report fields: id,job_id,category,created_at,expected,observed,project_id,current_state. IDs are decimal strings. Reports are sanitized client observations, not verified failures. Dashboard jobs have suspect and diagnostic_count; execution state remains independent.
Read existing UI patterns before editing. Read applicable UI skill and /home/ngosi/.agents/skills/writing-for-agents/SKILL.md before guidance edits. Verify library-specific APIs through current documentation when needed.

## Files
Create:
- server/web/src/screens/Diagnostics.jsx
- server/web/src/screens/Diagnostics.test.jsx
Modify only:
- server/web/src/App.jsx
- server/web/src/App.test.jsx
- server/web/src/api.js
- server/web/src/api.test.js
- server/web/src/components/Sidebar.jsx
- server/web/src/components/JobDetails.jsx
- server/web/src/components/JobDetails.test.jsx
- server/web/src/screens/Jobs.jsx
- server/web/src/screens/Jobs.test.jsx
- server/web/src/screens/ProjectDetail.jsx
- server/web/src/screens/ProjectDetail.test.jsx
- server/web/src/styles/app.css
- server/web/src/integration/dashboard-flow.test.jsx
- server/README.md
- plugin/skills/coordinating-multi-model-work/references/tool-contract.md
- plugin/skills/coordinating-multi-model-work/references/review.md
- plugin/tests/test-contracts.sh
Append only to this phase notes.md and journal.md. Include both in ERP FILES MODIFIED.

## Done When
- All Phase 3 acceptance criteria and reviewer checks in PLAN.md hold.
- Filter changes reset pagination and ignore stale responses, including route changes.
- Each report displays ID, timestamp, category, expected/observed text, job link, explicitly current execution state.
- Untrusted report text is rendered as text, never HTML.
- Keyboard access, labels, non-color indicators and loading/empty/unavailable/refresh-failure states have tests.
- Retention follows prune_history using job updated_at; reports and dedup evidence can vanish while jobs remain.
- Existing tool-contract line-count guard is preserved.
- Genuine RED then GREEN evidence for changed behavior.
- cd server && uv run --extra dev pytest -q
- cd server/web && npm test
- build_dir=$(mktemp -d /tmp/refract-diagnostics-build.XXXXXX) && (cd server/web && npm run build -- --outDir "$build_dir")
- bash plugin/tests/run.sh
- git diff --check

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
No Git commits, deployment, daemon restart, live probes, schema/dependency changes, generated assets, unrelated plans, secrets or hooks changes. Do not change execution state semantics, transcript handling or existing MCP contracts. No automatic recovery or new streaming system.
Use background execution for long validations where available. Coordinator reruns all checks independently in background.

## Response Format
Return full ERP # EXTERNAL RESPONSE and matching completion line. Include every touched path and concrete test results. If incomplete, return CONTINUE_CONTEXT or BLOCKED truthfully.
