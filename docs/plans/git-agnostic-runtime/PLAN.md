# Git-Agnostic Runtime — Plan

Design: `docs/plans/git-agnostic-runtime/DESIGN.md`

Sequenced so every phase leaves the tree compiling and tests green. Phase 1
removes Git behavior; Phase 2 removes the write-workflow surface; Phase 3 drops
the now-dead columns and model fields in schema v6.

---

### Phase 1: Git-agnostic job execution

**Task Guide Input:** Remove OpenMCP's ownership of Git from the runtime and
execution engine. Registration must accept any existing directory (not only a
clean Git repo). Job execution must run the backend in the project directory and
store the result without inspecting, committing, or resetting the worktree.
Delete the Git module entirely. Leave existing DB columns and method signatures
in place for now (pass empty placeholders). Distinct cases: register a non-Git
directory; run a job while the worktree has uncommitted changes; recover after a
daemon restart with an interrupted job (no reset).
**Profile:** `Resolve at execution`
**Goal:** The daemon runs jobs against any directory with no Git subprocess and
no worktree mutation.

**Files:**
- Delete: `src/openmcp/repositories.py`
- Delete: `tests/test_repositories.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/execution.py`
- Modify: `src/openmcp/server.py`

**Tasks:**
1. `runtime.register_project`: drop `inspect_repository` and the clean-check;
   validate the path is an existing directory (`Path(path).expanduser().resolve()`,
   `is_dir`); alias falls back to `resolved.name`; call `upsert_project` with
   `head_commit=""`, `clean=True` (columns still present this phase). Remove the
   `repositories` import.
2. `execution.JobRunner.run`: remove the clean-check, `base_commit` capture,
   `commit`, `reset`, read-only verify, and the finally-block re-inspect +
   `upsert_project`. Call `start_job(job_id, "")`; on success
   `finish_job(job_id, "succeeded", text=..., commit="", target_id=...)`; on
   non-success keep the existing `final_state` selection and
   `finish_job(job_id, final_state, error=...)`. Remove the `repositories`
   import and the now-unused `get_workflow`/`inspect_repository` usage.
3. Delete `JobRunner.recover`; in `runtime.start` drop the recovery loop
   (keep `interrupt_active_jobs()` then `scheduler.start(queued_jobs())`).
   `server.client_instructions` returns the resolved directory path (validate
   `is_dir`), remove its `repositories` import. Delete `repositories.py` and
   `tests/test_repositories.py`.

**Acceptance Criteria:**
- Registering a plain (non-Git) directory succeeds.
- A job whose worktree has uncommitted changes reaches `succeeded`; the tree is
  left unchanged by OpenMCP.
- An interrupted job stays `interrupted` after restart with no reset attempted.
- No `git` subprocess is spawned anywhere in `src/openmcp`.

**Reviewer Checklist:**
- No remaining reference to `repositories`, `inspect_repository`, `commit(`, or
  `reset(` in `src/openmcp`.
- Cancellation and closing paths still map to `cancelled` / `interrupted`
  correctly without the removed Git branch.
- `runtime.start` no longer calls `recover`; interrupted jobs are not reset.
- No dead imports left in `runtime.py`, `execution.py`, `server.py`.

**Verification Checks:**
- `python -m pytest tests/test_execution.py tests/test_server.py tests/test_smoke.py`
- `tgrep -n "repositories|inspect_repository" src/openmcp || echo NONE`

**Commit:** `refactor(runtime): make job execution git-agnostic`

---

### Phase 2: Remove commit_message and write distinction

**Task Guide Input:** Remove the write-versus-read workflow distinction and the
`commit_message` parameter across the workflow definitions and public API. The
client owns commit messages now, so OpenMCP neither validates nor stores them.
Keep the DB columns physically present for this phase (they default to empty);
they are dropped in the schema phase. Distinct cases: submit each workflow
(implement, review, consult) with only a prompt; confirm an empty prompt is
still rejected.
**Profile:** `Resolve at execution`
**Goal:** No `commit_message` or `workflow.writes` remains in the workflow,
runtime, or server surface.

**Files:**
- Modify: `src/openmcp/workflows.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/server.py`
- Modify: `src/openmcp/database.py`
- Modify: `tests/test_workflows.py`

**Tasks:**
1. `workflows.py`: drop the `writes` field from `WorkflowDefinition`; update the
   `_WORKFLOWS` entries; change `validate_request(workflow, prompt) -> str`
   returning the resolved prompt only (remove the `commit_message` guard).
2. `runtime.submit`: drop the `commit_message` parameter; call
   `validate_request(workflow, prompt)`; call `create_job` without
   `commit_message`. `database.create_job`: drop the `commit_message` parameter
   and omit the column from the INSERT (column stays, defaults to `''`).
3. `server.job_submit`: drop the `commit_message` argument. Update
   `tests/test_workflows.py` for the new `validate_request` signature.

**Acceptance Criteria:**
- All three workflows submit successfully with only a prompt.
- Empty/whitespace prompt is rejected by `validate_request`.
- No `commit_message` argument exists in `submit`, `job_submit`, or
  `create_job`; `WorkflowDefinition` has no `writes` attribute.

**Reviewer Checklist:**
- No caller still passes `commit_message` or reads `workflow.writes`.
- `create_job` INSERT omits `commit_message` and relies on the column default.
- Public MCP tool signature change in `server.job_submit` is intentional and
  documented in the diff.

**Verification Checks:**
- `python -m pytest tests/test_workflows.py tests/test_server.py tests/test_smoke.py`
- `tgrep -n "\.writes|commit_message" src/openmcp || echo NONE` (expect matches
  only in `database.py` schema DDL until Phase 3)

**Commit:** `refactor(workflows): drop commit_message and write distinction`

---

### Phase 3: Schema v6 drops dead Git columns

**Task Guide Input:** Advance the SQLite schema to version 6, dropping the Git
columns that are no longer written: `jobs.base_commit`, `jobs.result_commit`,
`jobs.commit_message`, `projects.head_commit`, `projects.clean`. Keep
`jobs.result_text` (the client-readable result). Provide a portable table-rebuild
migration from v5 that preserves all existing rows, trim the affected method
signatures and row readers, and remove the matching model fields. Distinct
cases: fresh database creates the v6 shape directly; an existing v5 database
upgrades in place with rows preserved.
**Profile:** `Resolve at execution`
**Goal:** The schema, DB methods, and models carry no Git fields; a v5 database
migrates cleanly to v6.

**Files:**
- Modify: `src/openmcp/database.py`
- Modify: `src/openmcp/models.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_dashboard.py`

**Tasks:**
1. `database.py`: set `_SCHEMA_VERSION = 6`; `_create_schema` emits `jobs`
   without `base_commit`/`result_commit`/`commit_message` and `projects`
   without `head_commit`/`clean`; add a v5→v6 table-rebuild in `_migrate`
   (create new → copy surviving columns → drop → rename), guarded so v6 is a
   no-op.
2. Trim methods and readers: `upsert_project` (no `head_commit`/`clean`),
   `_project_view`, `start_job` (no `base_commit`), `finish_job` (no `commit`),
   `reset_retry` (drop `base_commit`/`result_commit`), and the `job()` reader
   (`JobResult` without `commit`, `JobView` without `base_commit`). Update the
   Phase 1/2 call sites that passed placeholders.
3. `models.py`: drop `JobView.base_commit`, `JobResult.commit`,
   `ProjectView.head_commit`, `ProjectView.clean`.
4. Update `tests/test_database.py` (add a v5→v6 migration + row-preservation
   test) and any `tests/test_dashboard.py` assertions referencing dropped
   fields.

**Acceptance Criteria:**
- A fresh database reports `user_version=6` with the trimmed schema.
- A populated v5 database upgrades to v6: dropped columns gone, all job and
  project rows preserved.
- `JobView`, `JobResult`, and `ProjectView` expose no Git fields.
- Full test suite passes.

**Reviewer Checklist:**
- Migration is a table rebuild (no reliance on `ALTER TABLE DROP COLUMN`), runs
  inside a transaction, and preserves row counts and ordering-independent data.
- No reader still selects a dropped column; no model construction references a
  removed field.
- Dashboard/server responses no longer surface `head_commit`, `clean`, or
  `base_commit`.

**Verification Checks:**
- `python -m pytest`
- `tgrep -n "base_commit|result_commit|head_commit|commit_message|\.writes|inspect_repository|repositories" src/openmcp || echo NONE`

**Commit:** `refactor(db): drop dead git columns in schema v6`
