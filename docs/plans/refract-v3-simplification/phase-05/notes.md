# Phase 5 notes

Status: complete

Execution mode: direct, per owner on 2026-11-04. No coordinator, no Refract jobs, no review gates. Claude subagents in the same worktree may do large rewrites; the coordinator reruns all checks before each commit.

## Baseline

Commit `d3b12b51`, base ref `phase-05/base` = `447fb542`.

- PYTEST: 1114 passed, 15 deselected.
- PLUGIN: pass.
- LINES: 11746.

## Owner decisions

- 2026-11-04: the v3 `jobs` table keeps one column beyond the DESIGN.md list, `execution_plan_json`. Queued jobs run the plan fixed at submit time, as before. `config_revision`, `attempts`, `result_text`, `result_metadata_json`, and `telemetry_state_json` are dropped. DESIGN.md is updated to list the column.

## Step plan

- 5A: fresh v3 storage. One `_create_schema` with `projects`, `jobs`, `sessions`, `target_sessions`, `target_health` per DESIGN.md plus `jobs.execution_plan_json`. A database whose `user_version` is not the v3 version is renamed with its `-wal` and `-shm` files to `*.v2.bak`, then a fresh schema is created. All migrations, `events`, `context_turns`, `context_sessions`, `error_reports`, and `projects.alias` are deleted. Result text is read from `results/<job_id>.md`. Failure kind, model, duration, and six `tok_*` columns replace `result_metadata_json`; `result_metadata.py` is deleted. Tokens come from the existing accumulator snapshot at finish, null when unknown. Live output appends to `streams/<job_id>.jsonl` at 0600 with an in-memory tail, and pruning deletes the job row with its stream and result files. `streaming.py`, `StreamRecorder`, `JobStreamHub`, and `job_stream_events` are deleted. The stream work was planned as its own step; it moved into 5A because the exact v3 table set cannot hold while `job_stream_events` is still written.
- 5B: flat telemetry. `telemetry.py` becomes six nullable integer counters fed by backend outcomes. The measurement model is deleted.
- 5C: worker group cleanup. `jobs.pgid` is recorded at launch. At startup, each job marked `interrupted` has its group killed, guarded against a reused group ID.
- 5D: docs. `server/README.md` telemetry and streaming sections and the `server/CLI_ARGUMENTS.md` telemetry section describe flat tokens and stream files.

## Step 5A: fresh v3 storage and stream files

Status: complete.

### RED

`server/tests/test_storage_v3.py`, 7 tests written before any source change, all failed for the expected reasons on `d3b12b51`: v2 retirement with byte-equal `-wal` and `-shm` backups, v3 reopen untouched, exact tables and columns, null unknown tokens, result text from file, stream JSONL at 0600 with memory tail, pruning deletes row and both files.

During verification a gap was found: a database with a schema newer than v3 was renamed to `.v2.bak`. The removed test `test_unsupported_schema_is_rejected_without_writes_or_connection_leaks` had covered it. `test_newer_schema_database_is_refused_without_changes` failed on the subagent output, then passed after the guard was added.

### GREEN

- PYTEST: 800 passed, 15 deselected.
- PLUGIN: pass.
- LINES: 10535.
- ruff F: no new findings, 11 HEAD findings gone.

### Changes

- `database.py`: one fresh schema at `user_version` 18, no migrations. `_probe_version` reads a scratch copy so the original files are never opened before the rename. `_retire` renames the database and its sidecars to `*.v2.bak`, sidecars first, and refuses when a backup already exists. A newer schema is refused without changes. `finish_job` stores failure kind, model, duration and flat tokens. Streams append to `streams/<job_id>.jsonl`. `prune_history` deletes rows with their stream and result files.
- `models.py`: `JobResult` replaces the metadata groups; `JobView` drops `config_revision` and `attempts`.
- `execution.py`, `runtime.py`, `server.py`, `notifications.py`: use direct stream appends and flat result fields. MCP response shapes unchanged.
- Deleted `streaming.py`, `tests/test_streaming.py`, `tests/test_result_metadata.py`.

### Tests removed

123 test functions. All pin deleted behavior: schema 15, 16 and 17 migrations and preflight, the events and stream tables, metadata merge and measurement provenance, config revision, project aliases, stream cursor reload and truncation markers. Surviving behavior was ported.

### Deviations

- Done by a Claude subagent in the worktree; the coordinator reran all checks and audited the removed tests.
- `result_metadata.py` remains as a one-line re-export of `FAILURE_KINDS` and `runtime.live_result_metadata` keeps its name. Both go in 5B, where the acceptance grep must be empty.
- `server.py` `_ERROR_CODES` still lists `alias_taken`, which nothing raises. Removed in 5B.

### Debt

- A crash between sidecar and main renames leaves a `.v2.bak` sidecar; the next start refuses with a clear message instead of guessing. Manual cleanup is needed in that case.
- No test covers a stream write failure; the code logs and continues, as v2 did.

## Step 5B: flat token counters

### RED

- `tests/test_telemetry.py` rewritten as the `TokenCounters` contract: six nullable counters, per-response replacement, backend totals override, latest context wins, `clear_context()` keeps the window, invalid values ignored. Failed on import.
- `tests/test_streaming_backends.py::test_fixture_usage_produces_flat_tokens_matching_v2_totals` pins each backend's token totals on the four usage fixtures, captured from the v2 accumulator before the change. `test_backend_without_usage_reports_all_tokens_unknown` pins all six keys `None`. Both failed on the missing `tokens` field.

### GREEN

- PYTEST 777 passed, 15 deselected. PLUGIN pass. LINES 9362, down from 10536.
- Acceptance grep `job_stream_events|StreamRecorder|JobStreamHub|observed_at|context_turns|result_metadata` over `server/src`: empty.
- `Measurement|TelemetryAccumulator|TelemetryData|\.quality\b` over `server/src`: empty.
- ruff F: no new findings, 29 against 30 at HEAD.
- GREEN written by a Claude subagent in this worktree; the coordinator reran every check above before commit.

### Changes

- `telemetry.py` is now `TokenCounters` only. The measurement model, accumulator, attempt aggregate and attribution are deleted.
- `BackendResult` and the normalized driver result carry `tokens` with six keys; `telemetry` is gone. All four backends feed `TokenCounters`.
- `telemetry.updated` stream events carry only known flat token keys.
- 5A leftovers: `result_metadata.py` deleted, `FAILURE_KINDS` imported from `models.py`; `runtime.live_result_metadata` renamed `live_routing`; `alias_taken` removed from `server._ERROR_CODES`.
- Tests: 32 measurement-model tests replaced by the new `test_telemetry.py`; `test_retry_accumulator_rollover_failure_releases_probe` deleted because the rollover step no longer exists; the parametrized finalization-fault test still covers probe release on storage, health and revoke faults. Driver, backend and execution token tests ported to flat keys.

### Deviations

- After context invalidation the job keeps its context window. v2 stored `None`. The window is model capacity, which compaction does not change. Three assertions changed from `None` to `64000`.
- The backend-level context estimate is removed. The job-level estimate in `execution._job_tokens` stays, so stored job values match v2.
- Codex, pi and agy now emit one full snapshot per `telemetry.updated` event, so fewer events than v2. No consumer depends on event count. Claude's event sequence is unchanged.
- Quality, completeness and remaining-percent assertions dropped with the fields.

### Debt

- `server/README.md` and `server/CLI_ARGUMENTS.md` still document the old telemetry fields. Step 5D.

## Step 5C: worker process groups after a crash

### RED

- New `tests/test_worker_groups.py`, skipped where `/proc` is missing.
- `test_worker_runs_with_job_id_and_records_process_group` failed: the worker saw no `REFRACT_JOB_ID` and `jobs.pgid` stayed null.
- `test_restart_kills_worker_group_of_interrupted_job` failed: after a simulated restart the fake worker group kept running.
- `test_restart_leaves_group_without_matching_job_id`, parametrized with no marker and another job's ID, passed on HEAD as characterization and still passes.

### GREEN

- PYTEST 781 passed, 15 deselected. PLUGIN pass. LINES 9428. ruff F no new findings.

### Changes

- `backends/_process.py`: `spawn_hook` context variable; `run_process` awaits it with the child PID inside the kill-on-exit block.
- `execution.py`: sets the hook around `drivers.execute` to store the PGID through `Database.set_pgid`; a storage error is logged and does not fail the job. The worker env always carries `REFRACT_JOB_ID`.
- `processes.py`: `kill_stale_group(group_id, job_id)`.
- `runtime.start`: after marking running jobs interrupted, calls `kill_stale_group` for each recorded PGID and logs `job.worker_group` with the result.

### Guard against PGID reuse

A PGID can belong to an unrelated process once the old group is gone. The daemon scans `/proc` for members of the group and sends `SIGKILL` only when a member's environment contains `REFRACT_JOB_ID=<job_id>`. Job IDs are UUIDs, so a match identifies the job's own worker tree. Without `/proc`, as on macOS and Windows, nothing is killed and the log shows `killed: false`.

### Deviations

- The PGID reaches the database through a context variable instead of a new parameter on `DriverRegistry.execute`, `BackendParams` and the four backend call sites. Fewer signatures change, and test fakes keep working.
- Stale groups get `SIGKILL` at once. Their daemon is gone, so a graceful `SIGTERM` window adds nothing.

### Debt

- macOS and Windows keep leaking worker groups after a daemon crash. A platform process table check would be needed there.

## Step 5D: docs

### Changes

- `server/README.md`: "Observability and Token Consumption" drops turns; "Database compatibility" describes the fresh v3 schema and the `*.v2.bak` rename; "Worker Live Dashboard Streaming" describes stream and result files; "Worker Telemetry and Context Measurement" becomes "Worker Telemetry" with the six counters.
- `server/CLI_ARGUMENTS.md`: the capability table uses the six counter names and drops `context_remaining_percent`; the semantics section describes flat counters and null for unknown.
- Claims checked against code: `wait` returns `result.tokens`; `_job_tokens` sums consumption, takes context from the latest attempt and lets `contextWindow` override.

### Debt

- Stream files have no size cap since `StreamRecorder` was deleted in 5A. The v2 caps were 20000 events or 8 MiB per job. Pruning still deletes the file with its job.

## Phase 5 acceptance

- PYTEST 781 passed, 15 deselected. PLUGIN pass. LINES 9428, down from 11746 at the phase start.
- `tests/test_storage_v3.py` opens a v2 fixture database and finds `*.v2.bak` files plus the v3 schema.
- `git grep -nE 'job_stream_events|StreamRecorder|JobStreamHub|observed_at|context_turns|result_metadata' -- server/src`: empty.
- `tests/test_worker_groups.py::test_restart_kills_worker_group_of_interrupted_job` starts a fake long-running worker group, simulates a restart and proves the group is killed.
- `streaming.py`, `tests/test_streaming.py` and `tests/test_result_metadata.py` are deleted.
