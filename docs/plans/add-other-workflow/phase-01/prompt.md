## Original User Request

Add `other` to the built-in workflows.

## Phase

Add explicit `other` routing across validation and discovery.

## Tasks

- task-1: Add `other` to fixed validation and discovery.
- task-2: Cover explicit and missing profile mappings.
- task-3: Prove plan, job, and context-role persistence.
- task-4: Update doctor guidance and public documentation.

## Context

Workflows are validated strings. Profiles map them directly to target
selections. Existing partial profiles are valid. `other` must not fall back to
another mapping. It has no special mutation or read-only behavior.

## Files

- `src/openmcp/workflows.py`
- `src/openmcp/server.py`
- `tests/orchestration_helpers.py`
- `tests/test_workflows.py`
- `tests/test_config.py`
- `tests/test_planning.py`
- `tests/test_execution.py`
- `tests/test_server.py`
- `README.md`
- `docs/plans/add-other-workflow/phase-01/notes.md`
- `docs/plans/add-other-workflow/phase-01/journal.md`

## Done When

- `BUILTIN_WORKFLOWS` contains four ordered names.
- `get_workflow("other")` succeeds.
- Existing profiles without `other` still load.
- Unmapped `other` submissions fail clearly.
- Mapped `other` plans and jobs execute normally.
- Jobs and context history retain the `other` role.
- MCP discovery and doctor guidance expose `other`.
- README shows an explicit `other` mapping.
- No fallback routing or database migration appears.
- `uv run pytest tests/test_workflows.py tests/test_config.py tests/test_planning.py tests/test_execution.py tests/test_server.py`
- `uv run pytest`
- `uv build`
- `tgrep -n "\"other\"|other =" src/openmcp tests README.md -g "*.py" -g "*.md"`
- `tgrep -F "implement, review, and consult" src/openmcp tests README.md -n`
- The stale three-workflow search returns no matches.
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Use RED then GREEN.
Preserve existing partial-profile behavior. Maintain this phase's `notes.md`
and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
