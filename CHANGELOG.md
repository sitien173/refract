# Changelog

## 2.1.0 - 2026-10-29

- Added a `checklist` field to the `.handover.md` schema for tracking current-phase steps; `executing-plans` writes and maintains it.
- Added `plugin/scripts/refract-stats` to summarize open plans, with `--statusline` and `--hook` modes, and SessionStart, PostToolUse, and Stop hooks that show the summary.
- Added optional Langfuse tracing for job activity and MCP tool calls, with operator configuration and content-upload guidance.

## 2.0.0 - 2026-10-22

- Removed the `job_submit` `depends_on` parameter and the `job_cancel` `cancelled_dependents` return field.
- Removed `depends_on`, `waiting_on`, and `waiting_reason` from job summaries.
- Removed the `invalid_dependency` and `dependency_failed` error codes; unknown tool arguments now return `invalid_request`.
- Removed the `[daemon].max_project_readers` setting and parallel-read admission; admission is now one job per project, FIFO within each project.
- Removed `PUT /dashboard/api/settings`.
- Schema v14 migration cancels queued jobs whose dependencies had not succeeded and drops `job_dependencies` and `jobs.access_mode`.
- Before restarting, delete `[daemon].max_project_readers` from your configuration if present.

## 1.2.0 - 2026-10-12

- `executing-plans`: removed the consult step and the first, resumed, and fix submission templates from `implementer-prompt.md`; phase prompts drop the `SKILLS` section and use minimal rules.
- `writing-plans`: removed the recommended phase-detailing consult step.
- Phase prompt `Rules` now carry absolute pointers to the bundled worker contract, ERP, and templates; Gate 2 job prompts name the phase prompt path.
- Gate 1 no longer consults: the route is `implement -> review`, and handover drops `guidance.consult` and `job_refs.latest_consult`. `brainstorming` still uses `consult`.

## 1.0.0 - 2026-10-08

- Refract 1.0.0 combines the plugin, server, and dashboard under one product name.
- Lineage: superpowers-ccg 12.0.0 and openmcp 2.0.0.
