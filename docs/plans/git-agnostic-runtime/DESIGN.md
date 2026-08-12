# Git-Agnostic Runtime — Design

## Purpose

Remove OpenMCP's ownership of Git. Today the daemon requires a clean worktree,
captures a base commit, and commits or resets around every job. That mutation
layer makes client-side integration hard during active development.

Invert ownership: the client controls all Git mutation (cleanliness, commit,
reset). OpenMCP shrinks to routing requests to the backend and storing job
records the client can read back. The core runtime facade, scheduler, execution
engine, and driver/backend layer stay intact.

## Decisions

- Git-agnostic: delete `repositories.py` entirely. No Git subprocess anywhere.
- No new storage: reuse existing job records only.
- Schema v6: drop the now-dead Git columns and model fields.
- Strip both `commit_message` and `workflow.writes`; drop the read/write
  distinction.
- Per-project FIFO serialization (`scheduler.py` `_active_projects`) remains the
  sole concurrency guard. The clean-worktree check was never a race guard, so
  removing it introduces no concurrent-write hazard.

## Non-goals

- No client-facing Git API (commit/reset endpoints). The client owns Git with
  its own tooling; OpenMCP does not proxy Git commands.
- No new persisted fields or tables.
- No change to scheduler, `TargetExecutor`, drivers, or backend contracts.

## Data flow (after)

1. `register_project(path)` — validate directory, store `root`.
2. `submit(...)` — validate prompt, resolve plan, `create_job`, enqueue.
3. `JobRunner.run` — `start_job` → run `TargetExecutor` in `cwd=root` → store
   result text or error. The working tree is left as the backend left it.
4. Client reads the job record, then commits/resets on its own.

## Section A — Project registration (`runtime.register_project`)

- Remove `inspect_repository` and the clean-check.
- Validate: `Path(path)` expands/resolves; must be an existing directory
  (`is_dir`), else `OrchestrationError`.
- `resolved_alias = alias.strip() or resolved.name`.
- `upsert_project(id, alias, root=resolved.as_posix())` — no `head_commit`,
  no `clean`.
- Keep the `sqlite3.IntegrityError` handling for duplicate alias/root.

## Section B — Job execution (`execution.py` `JobRunner.run`)

- Remove `inspect_repository`, clean-check, `base_commit`, `commit`, `reset`,
  read-only verify, and the finally-block re-inspect + `upsert_project`.
- Flow:
  1. Load queued record; load project (fail job if project removed).
  2. `start_job(job_id)`.
  3. `plan = parse_execution_plan(...)`.
  4. `execution = await self.targets.execute(..., cwd=root, ...)`.
  5. On `SUCCESS` and not cancelled: `finish_job(job_id, "succeeded",
     text=execution.result.text, target_id=execution.target_id)`.
  6. Else: `final_state = interrupted if (cancelled and is_closing) else
     cancelled if cancelled else failed`; `finish_job(job_id, final_state,
     error=...)`.
- No worktree mutation. `TargetExecutor` is untouched.
- `get_workflow` import stays only if still needed; the `workflow.writes` branch
  is gone.

## Section C — Recovery (`runtime.start`, `JobRunner.recover`)

- Delete `JobRunner.recover`.
- `runtime.start`: `self.database.interrupt_active_jobs()` (marks running →
  interrupted) then `await self.scheduler.start(self.database.queued_jobs())`.
  No reset. Interrupted jobs stay interrupted; the client cleans up its tree.

## Section D — Workflows (`workflows.py` + callers)

- `WorkflowDefinition`: drop the `writes` field. Definitions become
  `WorkflowDefinition("implement", "code")`, etc.
- `validate_request(workflow, prompt) -> str`: drop `commit_message`; return the
  resolved prompt only. Remove the `commit_message`-vs-`writes` guard.
- `runtime.submit`: drop `commit_message` param; `resolved_prompt =
  validate_request(workflow, prompt)`; `create_job(...)` without
  `commit_message`.
- `server.job_submit`: drop the `commit_message` argument.

## Section E — Client instructions (`server.py`)

- Remove the `repositories` import.
- Line 98: return the resolved directory path (validate `is_dir`) instead of the
  Git toplevel.

## Section F — Models (`models.py`)

- `JobView`: drop `base_commit`.
- `JobResult`: drop `commit`.
- `ProjectView`: drop `head_commit`, `clean`.

## Section G — Database (schema v6)

- Bump `_SCHEMA_VERSION = 6`.
- Migration is a table rebuild (SQLite-portable): create new table, copy the
  surviving columns, drop old, rename.
  - `jobs`: drop `base_commit`, `result_commit`, `commit_message`. Keep
    `result_text` (the client-readable result).
  - `projects`: drop `head_commit`, `clean`.
- `_create_schema`: emit the v6 shape directly (no dropped columns); set
  `user_version=6`.
- Migration guard: detect v5 (columns present) and run the rebuild; already-v6
  is a no-op.
- Method signatures:
  - `start_job(job_id)` — drop `base_commit`.
  - `finish_job(job_id, state, *, text="", error="", target_id="")` — drop
    `commit`.
  - `upsert_project(project_id, alias, root)` — drop `head_commit`, `clean`.
  - `create_job(...)` — drop `commit_message`.
- Row readers (`job`, `job_record`, `project`, `queued_jobs`,
  `interrupt_active_jobs`) stop referencing the dropped columns.

## Testing

- Registration: a non-Git directory registers successfully; a dirty worktree is
  irrelevant. Missing/non-directory path errors.
- Execution: a job succeeds while the worktree has uncommitted changes; the tree
  is left dirty (OpenMCP does not commit or reset).
- Recovery: an interrupted job stays interrupted with no reset performed.
- Migration: v5 database with populated `base_commit`/`result_commit`/
  `head_commit`/`clean` upgrades to v6, columns removed, all rows preserved.
- Workflows: `validate_request` rejects empty prompt; no `commit_message`
  surface remains.
- Regression: grep confirms no `repositories`, `inspect_repository`, `commit(`,
  `reset(`, `base_commit`, `result_commit`, `head_commit`, `.writes`, or
  `commit_message` references remain in `src/openmcp`.

## Verification commands

- `python -m pytest tests/test_runtime.py tests/test_execution.py tests/test_database.py`
- Full suite: `python -m pytest`
- `tgrep -n "repositories|inspect_repository|base_commit|result_commit|head_commit|commit_message|\\.writes" src/openmcp`
