# Plan: Project Context Instructions

Design: [DESIGN.md](DESIGN.md)

Expose `context_init` so an MCP client can set a project-level and
workflow-level worker instruction, and have each backend worker receive it
through its own harness context mechanism without modifying any file Git tracks.

Phases 1 through 3 deliver a working feature for the claude and pi backends with
no file writes at all. Phase 4 adds the codex file path. Phase 5 adds agy and
documentation.

---

### Phase 1: Store and expose project context instructions

**Task Guide Input:** Add a durable per-project, per-workflow instruction store
to the OpenMCP daemon and expose it over MCP. This is a database schema change
plus one new MCP tool and one new resource. Use cases: a client sets an
implement instruction for a project; a client replaces it; a client clears it by
sending an empty string; a client reads back every stored instruction for a
project; a client sends an unknown project or workflow and receives an error.
Job execution is untouched in this phase.

**Goal:** `context_init` persists an instruction per project and workflow, and a
resource reads it back.

**Files:**
- Modify: `src/openmcp/database.py`
- Modify: `src/openmcp/models.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/server.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_server.py`

**Tasks:**
1. Add a `context_instructions` table keyed on `(project_id, workflow)` holding
   the instruction text and an updated timestamp, cascading on project delete.
   Bump `_SCHEMA_VERSION` to 7 and add the forward migration, which creates the
   table empty and moves no data.
2. Add `Database.set_context_instruction`, `Database.context_instruction`, and
   `Database.context_instructions`, where an empty instruction deletes the row.
3. Add `Runtime.set_context_instruction`, validating the project through
   `Database.project` and the workflow through `get_workflow`, both raising
   `OrchestrationError`.
4. Add the `context_init` MCP tool returning a `ContextInstructionsResult`
   model, and the `openmcp://projects/{project_id}/context_instructions`
   resource, following the shape of the existing project profiles resource.

**Acceptance Criteria:**
- A fresh database reports `PRAGMA user_version` of 7.
- A database at version 6 migrates to 7 with all existing projects, jobs,
  events, context sessions, context turns, and target health rows intact.
- Setting, replacing, and clearing an instruction round-trips through the
  resource.
- Clearing removes the row rather than storing an empty string.
- An unknown `project_id` or an unknown `workflow` raises.
- Deleting a project removes its instruction rows.

**Reviewer Checklist:**
- The v6 to v7 migration preserves every existing table and does not drop or
  recreate unrelated tables.
- The new table has a foreign key to `projects` with cascade delete.
- `context_init` validates the project before the workflow, matching
  `task_guide` error ordering.
- No job, execution, or driver code changed in this phase.

**Verification Checks:**
- `uv run pytest tests/test_database.py tests/test_server.py`
- `uv run pytest`

**Commit:** `feat(context): store project context instructions`

---

### Phase 2: Snapshot the instruction into the execution plan

**Task Guide Input:** Carry the stored instruction into the immutable per-job
execution plan so a later `context_init` cannot change a queued job. This is a
serialization change to an existing frozen dataclass that is persisted as JSON
in the `jobs.execution_plan_json` column, so backward compatibility with plans
written before this change is required. Use cases: submitting a job with an
instruction set; submitting with none set; parsing a plan record written by the
previous version; a `context_init` call landing between submit and execution.

**Goal:** Every job carries the instruction that was stored at submission time.

**Files:**
- Modify: `src/openmcp/planning.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `tests/test_planning.py`
- Modify: `tests/test_server.py`

**Tasks:**
1. Add an `instruction: str = ""` field to `ExecutionPlan` and include it in
   `execution_plan_data`.
2. Read `instruction` in `parse_execution_plan`, defaulting to `""` when the key
   is absent and rejecting a non-string value.
3. Have `Runtime.submit` read the stored instruction for the job's project and
   workflow and pass it into the resolved plan.

**Acceptance Criteria:**
- A plan with an instruction round-trips through
  `execution_plan_data` and `parse_execution_plan`.
- A plan JSON payload with no `instruction` key parses with an empty
  instruction.
- A non-string `instruction` raises `ValueError`.
- A job submitted after `context_init` carries the instruction in its stored
  plan.
- A `context_init` call after submission does not change the queued job's plan.
- `target_execution_key` is unchanged for a given target, so existing session
  continuity and target health rows still resolve.

**Reviewer Checklist:**
- `target_execution_key` hashes target data only and is not affected by the new
  plan field.
- Plans persisted by the previous version still parse.
- The instruction is read once at submission and never re-read during
  execution.

**Verification Checks:**
- `uv run pytest tests/test_planning.py tests/test_server.py`
- `uv run pytest`

**Commit:** `feat(context): snapshot instruction into execution plan`

---

### Phase 3: Inject the instruction into claude and pi

**Task Guide Input:** Deliver the snapshotted instruction to the claude and pi
harnesses using their repeatable `--append-system-prompt` flag, which is
additive and writes no files. The instruction must be threaded from the
execution plan through the target executor and driver registry into argv
compilation, and must be applied per attempt because a retry can select a
different backend. Use cases: a claude target with an instruction; a pi target
with an instruction; an isolated claude target using `--safe-mode`; an isolated
pi target using `--no-context-files`; a codex or agy target, which must be
unaffected in this phase; an empty instruction, which must add no flag.

**Goal:** claude and pi workers receive the instruction with no file written.

**Files:**
- Modify: `src/openmcp/drivers.py`
- Modify: `src/openmcp/execution.py`
- Modify: `CLI_ARGUMENTS.md`
- Modify: `tests/test_execution.py`

**Tasks:**
1. Add an `instruction` parameter to `_target_args` and to
   `DriverRegistry.execute`, defaulting to empty.
2. Append `--append-system-prompt <instruction>` for the `claude` and `pi`
   backends when the instruction is non-empty, placed after target `args` so a
   target cannot displace it.
3. Pass `plan.instruction` from `TargetExecutor.execute` into each
   `drivers.execute` call inside the attempt loop.
4. Document the injection mechanism per backend in `CLI_ARGUMENTS.md`, including
   that `--append-system-prompt` survives `--safe-mode` and
   `--no-context-files`.

**Acceptance Criteria:**
- A claude target with an instruction compiles argv containing
  `--append-system-prompt` followed by the instruction.
- A pi target with an instruction compiles the same pair.
- An isolated claude target compiles both `--safe-mode` and the append flag.
- An isolated pi target compiles both `--no-context-files` and the append flag.
- An empty instruction compiles argv identical to today's output for all four
  backends.
- codex and agy argv are unchanged regardless of the instruction.

**Reviewer Checklist:**
- The append flag is emitted after target `args`, not before.
- The instruction is never logged in full; existing logs record lengths only.
- The instruction is not passed through `validate_target_args`, which governs
  operator-supplied `args` only.
- A retry that selects a different backend recompiles argv for that backend.

**Verification Checks:**
- `uv run pytest tests/test_execution.py`
- `uv run pytest`

**Commit:** `feat(context): inject instruction into claude and pi`

---

### Phase 4: Materialize the codex context file

**Task Guide Input:** codex has no system-prompt flag, so its instruction must
arrive as a project document. Write a composed `AGENTS.override.md` at the
project root containing the instruction followed by the repository's own root
`AGENTS.md` inlined verbatim, because `AGENTS.override.md` shadows `AGENTS.md`
within a directory rather than adding to it. The file must be created fresh,
never written over anything Git tracks, hidden from Git through
`$GIT_COMMON_DIR/info/exclude` so it is invisible in every linked worktree, and
removed after the attempt including on failure, timeout, and cancellation. Use
cases: a repository with a root `AGENTS.md`; a repository without one; a
repository whose `AGENTS.override.md` is tracked by Git; an untracked foreign
file at that path; a leftover file carrying the daemon's own marker; a directory
that is not a Git repository; a crash between write and cleanup.

**Goal:** codex workers receive the instruction without shadowing project
guidance and without any Git-visible change.

**Files:**
- Create: `src/openmcp/context_files.py`
- Create: `tests/test_context_files.py`
- Modify: `src/openmcp/execution.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `tests/test_execution.py`

**Tasks:**
1. Add `context_files.py` with a marker header constant, a Git-tracked check, a
   managed-block writer for `$GIT_COMMON_DIR/info/exclude`, and a
   materialize and cleanup pair returning the paths it created.
2. Compose the codex `AGENTS.override.md` as the instruction followed by the
   repository's root `AGENTS.md` content when that file exists.
3. Wrap the `drivers.execute` call in `TargetExecutor.execute` so the file is
   written before the attempt and removed in a `finally` block, and return
   `REQUEST_FATAL` with the offending path when the target path is tracked, is
   an untracked foreign file, or the exclude file is not writable.
4. Sweep marker-bearing leftovers for a project on daemon start.

**Acceptance Criteria:**
- With a root `AGENTS.md` present, the generated file contains the instruction
  followed by that file's content verbatim.
- Without a root `AGENTS.md`, the generated file contains the instruction only.
- The generated path does not appear in `git status --porcelain` in the main
  checkout or in a linked worktree.
- The exclude block is written once and is not duplicated across repeated jobs.
- The file is absent after a successful attempt, a failed attempt, a timeout,
  and a cancellation.
- A tracked file at the target path fails the job `REQUEST_FATAL` and leaves the
  file byte-identical.
- An untracked foreign file at the target path fails the job `REQUEST_FATAL`.
- A leftover file carrying the marker is overwritten rather than refused.
- A non-Git project root still materializes and logs a warning.
- The startup sweep removes marker-bearing files and leaves all others alone.

**Reviewer Checklist:**
- Cleanup runs on every exit path, including cancellation and an exception
  raised inside the driver.
- The tracked check uses Git itself rather than inferring from `.gitignore`.
- The sweep deletes only files whose content carries the marker header.
- The exclude write targets `$GIT_COMMON_DIR/info/exclude`, resolved through
  Git, not a hard-coded `.git/info/exclude` path, so linked worktrees resolve
  correctly.
- No code path writes, stages, or commits a tracked file.
- The instruction is not logged in full.

**Verification Checks:**
- `uv run pytest tests/test_context_files.py tests/test_execution.py`
- `uv run pytest`

**Commit:** `feat(context): materialize codex context file`

---

### Phase 5: Materialize the agy context file and document the feature

**Task Guide Input:** agy reads `GEMINI.md` and `AGENTS.md` additively, so its
instruction needs no composition; a generated root `GEMINI.md` adds the
instruction without suppressing the repository's `AGENTS.md`. Reuse the Phase 4
materialization, tracked-file refusal, exclusion, and cleanup unchanged. Then
document the whole feature. One known limitation must be documented rather than
fixed here: agy loads project context only when the working directory is a known
agy project, and the adapter never passes `--new-project`, so a generated
`GEMINI.md` is ignored on the first job in a repository agy has not seen. Use
cases: an agy target with an instruction in a repository with no `GEMINI.md`; a
repository with a tracked `GEMINI.md`; a repository with both `AGENTS.md` and a
generated `GEMINI.md`.

**Goal:** agy uses the same file mechanism, and the feature is documented end to
end.

**Files:**
- Modify: `src/openmcp/context_files.py`
- Modify: `tests/test_context_files.py`
- Modify: `CLI_ARGUMENTS.md`
- Modify: `README.md`

**Tasks:**
1. Add the agy path: a generated root `GEMINI.md` containing the instruction
   only, reusing the existing refusal, exclusion, and cleanup behavior.
2. Document `context_init`, the resource, and the per-backend injection table in
   `README.md`.
3. Document the verified harness context-loading behavior and the agy
   `--new-project` limitation in `CLI_ARGUMENTS.md`.

**Acceptance Criteria:**
- A generated `GEMINI.md` contains the instruction only and no composed content.
- A repository with a root `AGENTS.md` keeps that file untouched when
  `GEMINI.md` is generated.
- A tracked `GEMINI.md` fails the job `REQUEST_FATAL`.
- The generated `GEMINI.md` does not appear in `git status --porcelain`.
- `README.md` documents the tool, the resource, and all four backend
  mechanisms.
- `CLI_ARGUMENTS.md` records the agy `--new-project` limitation explicitly.

**Reviewer Checklist:**
- The agy path shares the Phase 4 helpers rather than duplicating them.
- No composition is applied to the agy file, matching agy's additive loading.
- The documented limitation states that the agy path is inert until the
  directory is a known agy project.
- Documentation claims match the verified behavior in `DESIGN.md` and do not
  overstate agy support.

**Verification Checks:**
- `uv run pytest tests/test_context_files.py`
- `uv run pytest`

**Commit:** `feat(context): materialize agy context file and document`

---

## Out of scope

- Adding `--new-project` to the agy adapter. It changes behavior for every agy
  job, not only instructed ones, and needs its own scoped change. Until then the
  agy path is inert on a repository agy has not seen.
- Instruction templating or variable substitution.
- Per-target or per-model instructions.
- User-level or global instructions outside a project.
