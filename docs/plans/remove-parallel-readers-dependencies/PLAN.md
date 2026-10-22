# Remove Parallel Readers and Job Dependencies Plan

**Design:** `docs/plans/remove-parallel-readers-dependencies/DESIGN.md`
**Base:** `refs/plans/remove-parallel-readers-dependencies/base` (`ef78309`)
**Commit:** `feat!: remove parallel readers and job dependencies`

Baseline at `base`:

- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q`: 578 passed, 3 deselected.
- `cd /home/ngosi/projects/refract/server/web && npx vitest run`: fails intermittently. Run 1: 33 failed, 2 errors. Runs 2 and 3: 1 of 205 failed, a different test in `src/integration/dashboard-flow.test.jsx` each run. Phase 1 repairs this baseline. Prior plan `job-failover-metadata` recorded vitest flakes under host load as human-owned debt.
- `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh`: fails deterministically. `plugin/tests/test-contracts.sh:45` expects `{job:summary, result:{text, error, next_offset}}`; `tool-contract.md` documents `result:{text, error, next_offset, metadata}`. Phase 1 repairs this baseline.
- `git diff --check`: passes.

Out of scope for every phase: Git operations, secrets, `~/.refract` user config files, the live daemon and its database, `docs/diagrams/`, and any file under `docs/plans/` other than the current phase's `notes.md` and `journal.md`.

Each phase leaves all three suites green. Intermediate phases may leave the dashboard calling a removed server field or route; phase checkpoints are local and consolidate into one commit.

### Phase 1: Green baseline

**Task Guide Input:** Repair two baseline failures before feature removal. (a) A stale plugin contract assertion that omits `metadata` from the `job_wait` return envelope. (b) Intermittent failures in the web integration suite `server/web/src/integration/dashboard-flow.test.jsx`, a different test failing each run, found by systematic root-cause debugging rather than longer timeouts or retries. Use case: repository implementation of tests, with UI test code.
**Goal:** All three verification suites pass repeatedly at the plan base behavior.
**Files:**
- Modify: `plugin/tests/test-contracts.sh`
- Modify: `server/web/src/integration/dashboard-flow.test.jsx`, or the shared test setup or component under test if the root cause is there; record each extra path in `notes.md`
**Tasks:**
1. Update `plugin/tests/test-contracts.sh:45` so the expected `job_wait` return matches `tool-contract.md`: `{job:summary, result:{text, error, next_offset, metadata}}`. Change no other assertion.
2. Find the root cause of the intermittent `dashboard-flow.test.jsx` failures and fix it. Record the cause, the evidence, and the fix in `notes.md`.
**Acceptance Criteria:**
- `bash plugin/tests/run.sh` exits 0.
- `npx vitest run` passes three consecutive runs.
- No product behavior changes unless the root cause is in product code; `notes.md` states which.
**Reviewer Checklist:**
- The flakiness fix addresses a named root cause, not a timeout increase, retry, or skipped test.
- No plugin assertion is removed or weakened beyond the one envelope string.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server/web && npx vitest run && npx vitest run && npx vitest run`
- `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh`
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q`
- `cd /home/ngosi/projects/refract && git diff --check`

---

### Phase 2: Remove parallel readers from the server

**Task Guide Input:** Remove the parallel-reader feature from the Python daemon per the confirmed design. Distinct use cases: (a) scheduler admission returns to one job per project at a time, FIFO within a project, bounded by global `max_jobs`, keeping terminal-commit release through `complete(job_id, signal=False)` and `_terminal_waiters`; (b) remove access-class derivation and its driver verification helper; (c) remove the `max_project_readers` daemon setting, its configuration mutation, the dashboard settings output, and `PUT /dashboard/api/settings`. Dependency readiness (`is_ready`, `reevaluate`) and the `jobs.access_mode` column stay until Phase 3. Use case: non-UI repository implementation.
**Goal:** No reader or access-class logic remains in server code; `max_project_readers` is an unsupported daemon key.
**Files:**
- Modify: `server/src/refract/scheduler.py`
- Modify: `server/src/refract/planning.py`
- Modify: `server/src/refract/drivers.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/config_mutation.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_scheduler.py`
- Modify: `server/tests/test_planning.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_config_mutation.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_server.py`
**Tasks:**
1. In `scheduler.py`, remove `AccessMode`, `max_project_readers`, `_writer_barrier`, `_position`, and `_Dispatch.access_mode`, `workflow`, `context_key`, `session_scope`. `_schedule` selects the first ready pending dispatch whose project has no active dispatch. `enqueue(job_id, project_id)` takes only those arguments. Remove reader, barrier, and session branches from `waiting_reason`. Update callers in `runtime.py`.
2. Remove `derive_access_mode` from `planning.py` and `DriverRegistry.supports_verified_read_only` from `drivers.py`. In `database.py`, stop writing `access_mode` in the job insert and remove its validation and parameter; keep the column. Remove `access_mode` from `models.py` job models and `dashboard.py` job output.
3. Remove `max_project_readers` from `config.py` defaults, the supported `[daemon]` key set, and parsing; from `config_mutation.py`; from `models.py` settings models; and from `dashboard.py` settings GET output. Remove the `PUT /dashboard/api/settings` route and its update model.
4. Update tests: delete reader, barrier, session-scope, and `max_project_readers` tests. Add scheduler tests for one job per project, FIFO within a project, cross-project overlap up to `max_jobs`, and release at terminal commit. Add a config test that `[daemon].max_project_readers` is rejected as an unsupported daemon setting. Add a dashboard test that `PUT /dashboard/api/settings` no longer succeeds.
**Acceptance Criteria:**
- Two queued jobs in one project never run concurrently; jobs in two projects run concurrently when `max_jobs >= 2`.
- A second job in a project starts after the first job's terminal commit without waiting for the notifier.
- Loading a config with `[daemon] max_project_readers = 2` raises `Unsupported daemon settings`.
- `rg -n 'access_mode|parallel_read|max_project_readers|derive_access_mode|supports_verified_read_only|session_scope' server/src/refract --glob '!dashboard_static/**'` matches only `database.py` schema and migration lines for the retained column.
**Reviewer Checklist:**
- `complete(signal=False)`, `_terminal_waiters`, `cancel`, `wait`, `signal`, and `close` semantics are unchanged.
- Dependency readiness still gates admission; Phase 3 owns its removal.
- No test is deleted that covers behavior other than readers, barriers, session scope, or `max_project_readers`.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest tests/test_scheduler.py tests/test_planning.py tests/test_execution.py tests/test_database.py tests/test_config.py tests/test_config_mutation.py tests/test_dashboard.py tests/test_server.py -q`
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q`
- `cd /home/ngosi/projects/refract && git diff --check`

---

### Phase 3: Remove job dependencies and migrate the schema

**Task Guide Input:** Remove the job-dependency feature from the Python daemon and add schema migration v14 per the confirmed design. Distinct use cases: (a) persistence: migration `_migrate_v13_to_v14` cancels queued jobs with any non-succeeded dependency, drops `job_dependencies` and `jobs.access_mode`, and sets `user_version=14`; fresh schemas create the v14 shape; (b) runtime and scheduler: remove readiness, cascade cancellation, startup parent repair, waiting metadata, and the `dependency_failed` retry check; (c) MCP surface: remove `depends_on`, `cancelled_dependents`, the `invalid_dependency` and `dependency_failed` codes, the `depends_on`, `waiting_on`, and `waiting_reason` summary fields, and dependency text in instructions and tool descriptions. Use case: non-UI repository implementation with a database migration.
**Goal:** No dependency code remains in the server, and existing databases migrate to v14 safely.
**Files:**
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/scheduler.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/execution.py`, only if a terminal-callback consumer requires it
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/README.md`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_scheduler.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_dashboard.py`
**Tasks:**
1. In `database.py`, add `_migrate_v13_to_v14` in one `BEGIN IMMEDIATE` transaction: for each queued job with any dependency whose state is not `succeeded`, set state `cancelled`, error `Dependency <id> was removed before completion`, `updated_at`, and insert a `job.cancelled` event with `{"error": ...}` matching `finish_job`; then `DROP TABLE IF EXISTS job_dependencies`; then `ALTER TABLE jobs DROP COLUMN access_mode` when present; then `PRAGMA user_version=14`. Set `_SCHEMA_VERSION = 14`, call the step from `_migrate`, and remove the column and table from `_create_schema`. Replace `create_job_with_dependencies` with a plain job insert; remove `dependencies_for_job` and `dependents_for_job`.
2. In `scheduler.py`, remove `is_ready`, `reevaluate`, and `waiting_reason`. In `runtime.py`, remove `_dependencies_succeeded`, `_failed_dependency`, `_cancel_queued_dependent`, `_cancel_for_failed_parent`, `_cascade_unsuccessful`, `waiting_metadata`, and the startup repair loop; `_job_terminal` only calls `scheduler.complete(job_id, signal=False)`; `submit` drops `depends_on`; `cancel` drops `cancelled_dependents`; `retry` drops the `dependency_failed` check. Adjust `execution.py` only where the callback return value is consumed.
3. In `models.py`, remove `depends_on`, `waiting_on`, `waiting_reason`, and `ActionResult.cancelled_dependents`. In `server.py`, remove the `depends_on` argument and validation, the two error codes, `cancelled_dependents` from `job_cancel`, and dependency text from instructions and tool descriptions. In `dashboard.py`, remove dependency and waiting job fields. Update `server/README.md` to describe one-job-per-project FIFO admission and the reduced `job_submit` signature, and set its version line to `2.0.0`.
4. Update tests: delete dependency, cascade, waiting-metadata, `invalid_dependency`, `dependency_failed`, and `cancelled_dependents` tests. Add migration tests: a v13 database loses the column and table; a queued job with an unfinished dependency becomes `cancelled` with the error and one `job.cancelled` event; a queued job whose dependencies all succeeded stays `queued`; re-running migration is a no-op. Add a fresh-schema test and an MCP test that `job_submit` with `depends_on` returns `invalid_request` and summaries contain exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`.
**Acceptance Criteria:**
- A v13 fixture database migrates to `user_version=14` with no `access_mode` column and no `job_dependencies` table.
- The migration cancels exactly the queued jobs that had a non-succeeded dependency.
- `job_cancel` returns `{job:summary}` only.
- `rg -n 'depends_on|job_dependencies|cancelled_dependents|waiting_on|waiting_reason|dependency_failed|invalid_dependency|access_mode|is_ready|reevaluate' server/src/refract server/README.md --glob '!dashboard_static/**'` matches only `database.py` migration steps v11-to-v12 and v13-to-v14.
**Reviewer Checklist:**
- The migration is one transaction and rolls back on failure, matching existing steps.
- Startup recovery of interrupted jobs and the failover probe reset are unchanged.
- Terminal-commit admission release is unchanged.
- No error code other than the two named is removed.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest tests/test_database.py tests/test_scheduler.py tests/test_execution.py tests/test_server.py tests/test_dashboard.py -q`
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q`
- `cd /home/ngosi/projects/refract && git diff --check`

---

### Phase 4: Remove readers and dependencies from the dashboard

**Task Guide Input:** Remove the parallel-reader and job-dependency UI from the React dashboard to match the Phase 2 and 3 server API. Distinct use cases: (a) remove the Waiting and dependency columns and fields from job lists and job details; (b) remove the reader-capacity form and its settings mutation from runtime settings; (c) rebuild the packaged static assets. Use case: UI and client implementation.
**Goal:** The dashboard shows no reader or dependency UI and its packaged build matches source.
**Files:**
- Modify: `server/web/src/api.js`
- Modify: `server/web/src/api.test.js`
- Modify: `server/web/src/App.test.jsx`
- Modify: `server/web/src/components/JobDetails.jsx`
- Modify: `server/web/src/components/JobDetails.test.jsx`
- Modify: `server/web/src/hooks/useDashboardQuery.js`
- Modify: `server/web/src/screens/Jobs.jsx`
- Modify: `server/web/src/screens/Jobs.test.jsx`
- Modify: `server/web/src/screens/ProjectDetail.jsx`
- Modify: `server/web/src/screens/ProjectDetail.test.jsx`
- Modify: `server/web/src/screens/RuntimeSettings.jsx`
- Modify: `server/src/refract/dashboard_static/**`, generated by `npm run build` only
**Tasks:**
1. Remove `depends_on`, `waiting_on`, and `waiting_reason` columns, fields, sort accessors, and query handling from `Jobs.jsx`, `ProjectDetail.jsx`, `JobDetails.jsx`, and `useDashboardQuery.js`.
2. Remove the `max_project_readers` reader-capacity form, its settings PUT call in `api.js`, and the `knownDaemonKeys` entry in `RuntimeSettings.jsx`.
3. Update the listed tests to the reduced fields and settings, deleting only reader and dependency assertions. Run `npm run build` to regenerate `dashboard_static`.
**Acceptance Criteria:**
- `rg -n 'depends_on|waiting_on|waiting_reason|max_project_readers|access_mode|cancelled_dependents' server/web/src` returns no matches.
- `npx vitest run` passes three consecutive runs.
- `server/src/refract/dashboard_static` contains no match for `max_project_readers` or `waiting_reason`.
**Reviewer Checklist:**
- Remaining job columns, sorting, and settings tables behave as before.
- Static assets come from `npm run build`, not hand edits.
**Verification Checks:**
- `cd /home/ngosi/projects/refract/server/web && npx vitest run && npx vitest run && npx vitest run`
- `cd /home/ngosi/projects/refract/server/web && npm run build`
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest tests/test_dashboard.py -q`
- `cd /home/ngosi/projects/refract && git diff --check`

---

### Phase 5: Plugin contract, versions, and changelog

**Task Guide Input:** Update the Claude Code plugin documentation and contract tests to the reduced MCP surface, and release 2.0.0. Distinct use cases: (a) `tool-contract.md` tool table, summary fields, admission section, and error table; (b) the admission sentence in `coordinating-multi-model-work/SKILL.md`; (c) contract tests asserting the reduced surface; (d) version bump to 2.0.0 and a CHANGELOG entry. Use case: non-UI repository implementation of documentation, tests, and release metadata.
**Goal:** Plugin docs and tests describe the reduced surface, versions read 2.0.0, and no residue remains.
**Files:**
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/skills/coordinating-multi-model-work/SKILL.md`
- Modify: `plugin/tests/test-contracts.sh`
- Modify: `plugin/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `server/pyproject.toml`
- Modify: `server/uv.lock`
- Modify: `CHANGELOG.md`
**Tasks:**
1. In `tool-contract.md`: remove `depends_on=[]` from `job_submit`; set `job_cancel` returns to `{job:summary}`; set summary fields to exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`; replace the dependencies and admission section with one-job-per-project FIFO admission bounded by global capacity; remove `invalid_dependency` and `dependency_failed` from the error table. In `SKILL.md:43`, replace the reader/writer/session-fair admission sentence with one-job-per-project admission.
2. Update `test-contracts.sh` assertions that encode the removed surface, and add assertions that `depends_on`, `cancelled_dependents`, `invalid_dependency`, and `dependency_failed` are absent from `tool-contract.md`. Keep every unrelated assertion.
3. Set version `2.0.0` in `plugin.json`, `marketplace.json`, `server/pyproject.toml`, and the `refract` package entry in `server/uv.lock`. Add a `## 2.0.0 - <date>` CHANGELOG entry listing the removed parameter, return field, summary fields, error codes, daemon setting, dashboard settings route, and schema v14 migration, and instructing users to delete `[daemon].max_project_readers` before restart.
**Acceptance Criteria:**
- `bash plugin/tests/run.sh` exits 0.
- `rg -n 'depends_on|job_dependencies|cancelled_dependents|waiting_on|waiting_reason|dependency_failed|invalid_dependency|access_mode|parallel_read|max_project_readers' server/src/refract server/tests server/web/src plugin server/README.md README.md --glob '!dashboard_static/**'` matches only `server/src/refract/database.py` migration steps and Phase 3 migration tests in `server/tests/test_database.py`.
- All four version files read `2.0.0`.
**Reviewer Checklist:**
- The twelve remaining error codes and their next actions are unchanged.
- No plugin guard unrelated to the removed surface is weakened or deleted.
- CHANGELOG entry names every removed surface item.
**Verification Checks:**
- `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh`
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q`
- `cd /home/ngosi/projects/refract/server/web && npx vitest run`
- `cd /home/ngosi/projects/refract && git diff --check`
