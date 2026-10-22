# Remove Parallel Readers and Job Dependencies Design

**Status:** Confirmed 2026-10-22
**Consultation:** skipped - consult job 9e3dac29-cf98-41a9-9250-61e7874ee872 failed with `replay_blocked`, no `next_target`, not retryable; Coordinator inventory used instead.

## Purpose

Remove two v2 features introduced by `docs/plans/mcp-v2-claude-code/` Phases 2 to 5:

1. Parallel readers: `access_mode`, `derive_access_mode`, `max_project_readers`, and reader/writer/session-fair admission.
2. Job dependencies: `depends_on`, the `job_dependencies` table, cascade cancellation, `cancelled_dependents`, and derived waiting metadata.

Keep every other v2 capability: the seven-tool MCP surface, heartbeat waits, failover and circuit breaker, result metadata, and terminal-commit admission release.

## Users and Success Criteria

Users are operators and the Coordinator submitting jobs through MCP and the dashboard.

| Criterion | Required behavior |
|---|---|
| Admission | One job per project at a time, FIFO within a project, bounded by global `max_jobs` |
| Cross-project | Jobs in different projects overlap up to `max_jobs` |
| Terminal release | A project slot is released at terminal commit, before notifier completion |
| MCP surface | `job_submit` has no `depends_on`; `job_cancel` returns `{job:summary}` only |
| Summary fields | Exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at` |
| Error codes | `invalid_dependency` and `dependency_failed` no longer exist; twelve codes remain |
| Configuration | `[daemon].max_project_readers` is rejected as an unsupported daemon setting |
| Schema | Version 14 has no `jobs.access_mode` column and no `job_dependencies` table |
| Existing data | Queued jobs with an unfinished dependency are cancelled during migration |
| Residue | No production, test, or plugin file references the removed identifiers |
| Versions | Plugin, marketplace, and server are `2.0.0` with a CHANGELOG entry |

## Constraints and Non-Goals

### Constraints

- Simplify the current `scheduler.py`; do not restore the `c18bd69` scheduler verbatim, because that version releases admission only after the notifier await.
- Keep `complete(job_id, signal=False)`, `_terminal_waiters`, `cancel`, `wait`, `signal`, and `close` semantics.
- Unknown MCP arguments, including `depends_on`, fail through existing `invalid_request` validation without a special case.
- Migration follows the existing `BEGIN IMMEDIATE` step pattern in `Database._migrate`.

### Non-goals

- Historical `docs/plans/*` files stay unchanged.
- `docs/diagrams` C4 model files stay unchanged.
- No deprecation shim for `depends_on` or `max_project_readers`.
- No other scheduler, failover, or dashboard behavior change.
- No live daemon restart or live configuration edit by workers.

## Chosen Approach

Surgical removal: simplify the current scheduler, remove reader and dependency code from every layer by hand, and add schema migration v14.

- Rejected: `git revert` of the Phase 2 and 3 commits; they interleave with the Phase 4 and 5 v2 surface, later failover work, and the repository rename.
- Rejected: force every job to `exclusive`; leaves dead reader, barrier, and session logic.

## Architecture and Data Flow

| Component | Change |
|---|---|
| `server/src/refract/scheduler.py` | Remove `AccessMode`, `max_project_readers`, `is_ready`, `reevaluate`, `waiting_reason`, `_writer_barrier`, `_position`, and `_Dispatch.access_mode`, `workflow`, `context_key`, `session_scope`. `_schedule` selects the first pending dispatch whose project has no active dispatch. `enqueue(job_id, project_id)` |
| `server/src/refract/planning.py` | Remove `derive_access_mode` |
| `server/src/refract/drivers.py` | Remove read-only enforcement verification only if `derive_access_mode` is its sole consumer |
| `server/src/refract/runtime.py` | Remove `_dependencies_succeeded`, `_failed_dependency`, `_cancel_queued_dependent`, `_cancel_for_failed_parent`, `_cascade_unsuccessful`, `waiting_metadata`, and the startup repair loop. `_job_terminal` only calls `scheduler.complete(job_id, signal=False)`. `submit` drops `depends_on`; `cancel` drops `cancelled_dependents`; `retry` drops the `dependency_failed` check |
| `server/src/refract/execution.py` | Adjust only where the terminal callback return value or cascade behavior is consumed |
| `server/src/refract/database.py` | Replace `create_job_with_dependencies` with a plain job insert without `access_mode` or links. Remove `dependencies_for_job` and `dependents_for_job`. Remove `access_mode` and `job_dependencies` from `_create_schema`. Add `_migrate_v13_to_v14` |
| `server/src/refract/models.py` | Remove `depends_on`, `waiting_on`, `waiting_reason` from summary and `JobView` models, `ActionResult.cancelled_dependents`, `access_mode`, and settings `max_project_readers` |
| `server/src/refract/server.py` | Remove the `depends_on` argument and validation, the two error codes, `cancelled_dependents`, and dependency text in instructions and tool descriptions |
| `server/src/refract/config.py`, `config_mutation.py` | Remove `max_project_readers` |
| `server/src/refract/dashboard.py` | Remove `max_project_readers` settings output, `PUT /dashboard/api/settings`, and dependency job fields |
| `server/web/src` | Remove Waiting and dependency columns and fields and the reader-capacity form; rebuild `dashboard_static` |
| `plugin/` | Update `tool-contract.md` tool table, summary fields, dependencies and admission section, and error table; the admission sentence in `coordinating-multi-model-work/SKILL.md`; any `using-refract` mention; `tests/test-contracts.sh` |
| Versions | `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `server/pyproject.toml`, `server/uv.lock`, `CHANGELOG.md` |

## Errors and Edge Cases

- A client passing `depends_on` receives `invalid_request`.
- A configuration containing `[daemon].max_project_readers` fails startup with the existing `Unsupported daemon settings` error. CHANGELOG instructs removal of the key.
- Jobs cancelled by migration send no desktop notification; the notifier is not running during migration.
- Startup recovery of interrupted jobs is unchanged.

## Migration

`_migrate_v13_to_v14`, in one `BEGIN IMMEDIATE` transaction:

1. For each queued job with any dependency whose state is not `succeeded`, set state `cancelled`, error `Dependency <id> was removed before completion`, and `updated_at`, and insert a `job.cancelled` event with `{"error": ...}`, matching `finish_job` output.
2. `DROP TABLE IF EXISTS job_dependencies`; its index drops with it.
3. `ALTER TABLE jobs DROP COLUMN access_mode` when the column exists. Requires SQLite 3.35 or later; the local runtime reports 3.53.1.
4. `PRAGMA user_version=14`; `_SCHEMA_VERSION = 14`.

Fresh databases create the v14 shape directly. Migration completes before the scheduler starts, so cancelled jobs are never enqueued.

## Testing

Remove tests for reader/writer admission, barrier fairness, session scope, dependency readiness, cascade, waiting metadata, the two error codes, `cancelled_dependents`, and `max_project_readers`.

Add or keep:

- Scheduler: one job per project, FIFO within a project, cross-project overlap up to `max_jobs`, terminal-commit release, queued and running cancellation.
- Migration v13 to v14: column and table removed; queued job with an unfinished dependency cancelled with an event row; queued job whose dependencies all succeeded stays queued; idempotent re-run.
- Fresh v14 schema lacks the column and table.
- Configuration rejects `max_project_readers`.
- MCP: `job_submit` with `depends_on` returns `invalid_request`; summaries contain exactly the reduced field set.

Verification:

- `cd server && uv run --extra dev pytest -q`
- `cd server/web && npm test`
- `bash plugin/tests/run.sh`
- `git diff --check`
- `rg` residue check for `depends_on`, `access_mode`, `max_project_readers`, `parallel_read`, `waiting_on`, `waiting_reason`, `cancelled_dependents`, `invalid_dependency`, `dependency_failed` across `server/src`, `server/tests`, `server/web/src`, `plugin`, and READMEs, excluding `docs/plans` and `CHANGELOG.md`

## Risks and Open Questions

- Dependency links are deleted. Affected queued jobs are cancelled, not deleted.
- Connected MCP clients keep cached tool schemas until restart.
- The user restarts the daemon after deployment and first removes `max_project_readers` from the live configuration if present.
- SQLite older than 3.35 cannot run step 3 of the migration. No support for older versions is planned.
- Open questions: none.
