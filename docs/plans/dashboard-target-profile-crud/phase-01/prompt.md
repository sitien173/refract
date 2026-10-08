## Original User Request
Complete dashboard target-profile CRUD.

## Phase
Build a tested transaction boundary for safe TOML configuration writes.

## Tasks
- task-1: Add failing preservation, concurrency, path-safety, and atomicity tests.
- task-2: Add reusable candidate-loading and TOML document mutation primitives.
- task-3: Add synchronized commit, runtime publication, and rollback behavior.
- task-4: Verify new submissions use new catalogs while existing plans remain stable.

## Context
Read `docs/plans/dashboard-target-profile-crud/DESIGN.md` and Phase 1 in `PLAN.md`. Use `tomlkit` for surgical changes. Reuse existing configuration-loading semantics rather than defining a second schema. Do not expose HTTP routes.

## Files
- `src/openmcp/config_mutation.py`
- `src/openmcp/config.py`
- `src/openmcp/runtime.py`
- `src/openmcp/execution.py`
- `tests/test_config_mutation.py`
- `tests/test_runtime.py`
- `tests/test_execution.py`

## Done When
- Exact-byte SHA-256 revisions, stale-revision rejection, safe regular paths, source-directory atomic writes, mode preservation, candidate validation, publication, and proven rollback work.
- TOML comments, ordering, quoting, shorthand, and legacy keys remain preserved where `tomlkit` permits.
- New submissions use refreshed catalogs while submitted execution plans remain stable.
- `uv run pytest tests/test_config_mutation.py tests/test_runtime.py tests/test_execution.py -q`
- `uv run pytest tests/test_config.py tests/test_planning.py -q`
- `git diff --check`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
