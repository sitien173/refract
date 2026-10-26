## User Request
Complete Phase 4 dashboard telemetry, documentation, and packaged release assets. Implement test-first. Preserve existing transports and SQLite schema version 15.

## Phase
Make normalized live context and per-job consumption readable on both job-detail routes.

## Context
Read /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/DESIGN.md and PLAN.md completely. Phases 1 through 3 are independently reviewed. Existing telemetry is persisted in result metadata; measurements contain value, source, quality, observed_at. Read telemetry.py to establish the actual nested contract. Do not reinterpret legacy counters as normalized telemetry. Runtime backend capabilities remain unverified: no live probes are authorized.

## Tasks
1. Add failing rendering tests before implementation. Display Context used, Context capacity, Context remaining, Job input tokens, Job output tokens. Separate context from consumption. Distinguish unknown, reported zero, derived, estimated, and partial totals. Display quality, source, observation time, completeness, and cache components where supplied. Remaining percentage is unavailable without capacity. Historical jobs must not fabricate measurements.
2. Reuse current selected-job polling on canonical and legacy routes. Test initial loading, refreshed telemetry, running-to-terminal final persisted refresh, request failure/recovery, late responses after navigation, and transcript truncation. Do not add duplicate timers, telemetry SSE, or dependence on useJobStream retention/status.
3. Add integration/persistence coverage for terminal values, reload, transcript pruning, and historical jobs. Preserve transcript rendering, accessibility, keyboard access, and unrelated routing behavior.
4. Document normalized versus legacy semantics, cache accounting, observation/presentation timing, partial totals, backend capability limits, and opt-in probe limitations. Extend worker-facing metadata documentation without changing workflow rules. Restore this exact existing admission sentence required by plugin/tests/test-contracts.sh:
At most one job per project runs at a time. Jobs within each project are admitted FIFO, bounded by the global `max_jobs` capacity; jobs in different projects may run concurrently up to that capacity.
Inspect the assertion before editing.
5. Run all offline release checks. Generate packaged assets through the existing Vite build configuration. Preserve unrelated packaged assets; inspect generated output.

## Files
Only modify these implementation paths:
- server/web/src/components/JobDetails.jsx
- server/web/src/components/JobDetails.test.jsx
- server/web/src/hooks/useProjectDetail.js
- server/web/src/screens/ProjectDetail.test.jsx
- server/web/src/screens/JobDetail.jsx
- server/web/src/integration/dashboard-flow.test.jsx
- server/web/src/styles/app.css
- server/tests/test_dashboard.py
- server/tests/test_server.py
- server/tests/test_retention.py
- server/tests/test_live_backends.py
- server/README.md
- server/CLI_ARGUMENTS.md
- plugin/skills/coordinating-multi-model-work/references/tool-contract.md
- server/src/refract/dashboard_static/index.html
- server/src/refract/dashboard_static/assets/
Also append test evidence and ERP to this phase's notes.md and journal.md. Do not edit PLAN.md, DESIGN.md, .handover.md, or other phase artifacts. Read other source files as necessary. Ask before expanding scope.

## Done When
All Phase 4 acceptance criteria and reviewer checklist in PLAN.md hold.
- `cd server && uv run pytest`
- `cd server/web && npm test`
- `cd server/web && npm run build -- --outDir /tmp/refract-worker-job-telemetry-build`
- `bash plugin/tests/run.sh`
Packaged assets contain the panel and match the existing build configuration.
Record exact RED failures and GREEN counts for each behavior, commands, and log locations. Generated assets are exempt from test-first sequencing; source behavior is not.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
No Git writes, commits, resets, branch changes, or ref changes. Coordinator owns Git.
No live model probes, additional model requests for telemetry, credential reads, existing user-conversation inspection, global settings changes, schema migration, or transport replacement.
Keep unsupported values null. Never infer occupied context from cumulative consumption or invent capacities.
Read relevant writing-for-agents guidance before editing the worker contract reference. Use current library documentation only if library-specific API details require verification. Stay surgical.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line. Declare every changed file.
