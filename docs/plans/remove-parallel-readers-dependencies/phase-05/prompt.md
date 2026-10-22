## User Request
Remove parallel readers and job dependencies from Refract. Phases 2 to 4 removed them from the server and dashboard. This phase updates the plugin contract docs and tests, and releases 2.0.0.

## Phase
Plugin docs and tests describe the reduced surface, versions read 2.0.0, and no residue remains.

## Tasks
- task-1: In `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`: remove `depends_on=[]` from `job_submit`; set `job_cancel` returns to `{job:summary}`; set summary fields to exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`; replace the dependencies and admission section with one-job-per-project FIFO admission bounded by global capacity; remove `invalid_dependency` and `dependency_failed` from the error table. Also state that unknown tool arguments return `invalid_request`, which the server now enforces. In `plugin/skills/coordinating-multi-model-work/SKILL.md` near line 43, replace the reader/writer/session-fair admission sentence with one-job-per-project admission.
- task-2: Update `plugin/tests/test-contracts.sh` assertions that encode the removed surface, and add assertions that `depends_on`, `cancelled_dependents`, `invalid_dependency`, and `dependency_failed` are absent from `tool-contract.md`. Keep every unrelated assertion.
- task-3: Set version `2.0.0` in `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `server/pyproject.toml`, and the `refract` package entry in `server/uv.lock`. Add a `## 2.0.0 - 2026-10-22` entry at the top of `CHANGELOG.md`, matching the existing entry style, listing: removed `job_submit` `depends_on` parameter; removed `job_cancel` `cancelled_dependents` return field; removed `depends_on`, `waiting_on`, `waiting_reason` summary fields; removed `invalid_dependency` and `dependency_failed` error codes; unknown tool arguments now return `invalid_request`; removed `[daemon].max_project_readers` setting and parallel read admission, now one job per project FIFO; removed `PUT /dashboard/api/settings`; schema v14 migration cancels queued jobs whose dependencies had not succeeded and drops `job_dependencies` and `jobs.access_mode`. Instruct users to delete `[daemon].max_project_readers` from config before restart.

## Context
- Design: docs/plans/remove-parallel-readers-dependencies/DESIGN.md. Plan: PLAN.md Phase 5.
- Current versions: plugin.json 1.2.0, marketplace.json 1.2.0, server/pyproject.toml 1.0.0. server/README.md already reads 2.0.0.
- Server MCP descriptions in server/src/refract/server.py show the reduced surface; match them.

## Files
- Modify: plugin/skills/coordinating-multi-model-work/references/tool-contract.md
- Modify: plugin/skills/coordinating-multi-model-work/SKILL.md
- Modify: plugin/tests/test-contracts.sh
- Modify: plugin/.claude-plugin/plugin.json, .claude-plugin/marketplace.json
- Modify: server/pyproject.toml, server/uv.lock
- Modify: CHANGELOG.md
- Append only: docs/plans/remove-parallel-readers-dependencies/phase-05/notes.md and journal.md

## Done When
- `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh` exits 0.
- `rg -n 'depends_on|job_dependencies|cancelled_dependents|waiting_on|waiting_reason|dependency_failed|invalid_dependency|access_mode|parallel_read|max_project_readers' server/src/refract server/tests server/web/src plugin server/README.md README.md --glob '!**/dashboard_static/**'` matches only `server/src/refract/database.py` migration steps, Phase 3 migration tests in `server/tests/test_database.py`, the Phase 2 rejection test in `server/tests/test_config.py`, the Phase 3 rejection test in `server/tests/test_server.py`, and the new absence assertions in `plugin/tests/test-contracts.sh`.
- All four version files read `2.0.0`.
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q` passes.
- `cd /home/ngosi/projects/refract && git diff --check` passes.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Keep the twelve remaining error codes and their next actions unchanged. Do not weaken or delete any plugin guard unrelated to the removed surface.
- Edit `server/uv.lock` only for the refract version line.
- No Git writes. Do not read or edit secrets, `~/.refract`, the live daemon, or its database. Do not edit other files under `docs/plans/`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
