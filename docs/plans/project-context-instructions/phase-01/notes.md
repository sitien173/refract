<!-- ccg-shared-version: 10.1.0 -->

# Phase 1 — Decision Notes

## Task 1 — Schema version 7 and context instruction database operations

### Decisions made
- Added the `context_instructions` table to the shared `_create_support_tables`
  helper so every creation and migration path (fresh, v6, v5, legacy) ends with
  the table present. This matches how `events`, `context_sessions`,
  `context_turns`, and `target_health` are handled.
- The v6→v7 forward migration reuses the existing `_is_v6_schema` branch, which
  calls `_create_support_tables()` (idempotent `CREATE TABLE IF NOT EXISTS`)
  and then bumps `PRAGMA user_version` to 7. No data is moved.
- Registered `context_instructions` in `_columns()` so tests and introspection
  can inspect the table through the same helper used for other tables.
- `set_context_instruction` treats a non-empty instruction as an upsert and an
  empty instruction as a delete, so clearing removes the row instead of storing
  an empty string.
- `context_instructions` orders rows by `workflow` for deterministic output.

### Spec deviations
- none

### Tradeoffs accepted
- The v5 and legacy migration paths are not wrapped in their own
  `BEGIN IMMEDIATE` transaction for the new table, because the new table is
  created by the post-migration `_create_support_tables()` call; the existing
  migration transactions already commit before that call, matching the
  pre-existing pattern for the other support tables.

### Assumptions
- `context_instruction` returns `""` for a missing pair, matching the
  "clearing removes the row" model, so the read of a cleared pair is an empty
  string.

### Follow-ups for human
- none

### Test evidence
- RED: `uv run pytest tests/test_database.py -x -q` failed on
  `test_fresh_database_uses_v7_schema` with `assert 6 == 7`, then failed on the
  `_columns` helper with `ValueError: Unsupported schema table:
  context_instructions`.
- GREEN: `uv run pytest tests/test_database.py -q` -> `11 passed`.

## Task 2 — Runtime validation, MCP tool, resource, and result model

### Decisions made
- `Runtime.set_context_instruction` validates the project first via
  `Database.project`, raising `OrchestrationError` for an unknown project before
  touching the workflow, then validates the workflow via `get_workflow`, wrapping
  its `ValueError` into `OrchestrationError`. This matches `task_guide`'s error
  ordering (project before workflow) and the `submit` convention of converting
  `ValueError` to `OrchestrationError`.
- `Runtime.context_instructions` (resource backing) also validates the project
  and raises `OrchestrationError` for an unknown project, matching the other
  `openmcp://projects/{project_id}/...` resources.
- The `ContextInstructionsResult` model carries `project_id` and the full
  per-workflow `instructions` mapping, so the tool response echoes the stored
  state and the resource exposes the same shape.
- The resource is `openmcp://projects/{project_id}/context_instructions`,
  following the existing project profiles resource pattern
  (`openmcp://projects/{project_id}/profiles`).
- `context_init` accepts `(project_id, workflow, instruction)` as the tool
  parameters; an empty `instruction` clears the pair.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The resource JSON includes the `project_id` field because it serializes the
  `ContextInstructionsResult` model; the acceptance criterion "reads back every
  stored instruction for a project" is satisfied by the `instructions` mapping.

### Follow-ups for human
- none

### Test evidence
- RED: `uv run pytest tests/test_server.py -x -q` -> `ImportError: cannot
  import name 'ContextInstructionsResult' from 'openmcp.models'`.
- GREEN: all new `test_server.py` context_init/context_instructions tests
  pass; `uv run pytest tests/test_server.py -q` -> `22 passed, 4 failed` where
  the 4 failures are pre-existing on the base commit (see Task 3 evidence).

## Task 3 — Migration, persistence, validation, clearing, and cascade tests

### Decisions made
- Added `create_v6_database` helper so the v6→v7 migration is tested directly
  with real v6 rows (projects, jobs, events, context sessions, context turns,
  target health) and asserted intact after migration.
- Renamed the existing fresh-schema, v5-migration, and reopen tests from v6 to
  v7 expectations, and added a v5→v7 migration test asserting v6-era data is
  preserved and the `context_instructions` table exists empty.
- Added a schema-level cascade test via `PRAGMA foreign_key_list`
  (`on_delete == CASCADE` referencing `projects`) and a row-level cascade test
  that deletes the project and asserts the instruction rows disappear.
- Added a database-level integrity test proving `set_context_instruction` for an
  unknown project raises `sqlite3.IntegrityError` (foreign key), complementing
  the runtime-level `OrchestrationError` validation tests.
- Server tests cover set/replace/clear round-trip through the resource,
  per-workflow isolation, unknown project before workflow ordering, unknown
  workflow, unknown project on the resource, persistence across a daemon
  restart, and that `context_init` queues no jobs and mutates no job execution.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The verification command `uv run pytest tests/test_database.py
  tests/test_server.py` is expected to be green apart from the four pre-existing
  failures listed below; those failures exist on the base commit
  (`7097a18`) and are unrelated to this phase.

### Follow-ups for human
- Pre-existing failures on base commit `7097a18` (verified by stash):
  `test_mcp_exposes_direct_job_contract` (`timeout_s` default is 300, test
  expects 30) and `test_job_wait_bounds_public_timeout[None-30/0-30/45-30]`.
  Root cause: `server._MCP_WAIT_TIMEOUT_S = 300` while the tests expect a 30
  default. Fixing `job_wait` is out of scope for this phase (phase must not
  change job execution). Recommend a separate scoped change.

### Test evidence
- RED: new tests failed before implementation (Task 1 RED for schema; Task 2
  RED for model import; Task 3 tests depend on Tasks 1-2 code).
- GREEN:
  - `uv run pytest tests/test_database.py -q` -> `13 passed`.
  - `uv run pytest tests/test_database.py tests/test_server.py -q` ->
    `35 passed, 4 failed` (4 pre-existing).
  - `uv run pytest -q` -> `184 passed, 4 failed, 3 deselected` vs base commit
    `170 passed, 4 failed, 3 deselected`; the failing set is identical, so the
    phase adds 14 passing tests with zero regressions.
