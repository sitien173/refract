## Original User Request
Continue the profile-strategy-refactor plan through Phase 2 using the canonical
OpenMCP gates.

## Phase
Add explicit chained profile inheritance and permit partial profiles.

## Tasks
- task-1: Parse `extends` separately from workflow selections.
- task-2: Resolve inheritance chains lazily with memoization and cycle checks.
- task-3: Allow partial profiles and defer missing-workflow rejection.
- task-4: Implement replacement, cross-layer inheritance, and base self-extends.
- task-5: Preserve `extends` in config writing and update tests and documentation.

## Context
Phase 1 removed fabricated defaults and legacy routing. `_profiles()` remains
order-dependent, implicitly inherits the default profile, and enforces complete
built-in workflow mappings. `load_project_config()` passes the base default as
an implicit parent. Phase 2 replaces those behaviors with explicit single-parent
inheritance. Existing `resolve_execution_plan()` already rejects an unmapped
workflow at submission time.

## Files
- `src/openmcp/config.py`
- `src/openmcp/config_writer.py`
- `tests/test_config.py`
- `tests/test_planning.py`
- `README.md`
- `CLI_ARGUMENTS.md`
- `docs/plans/profile-strategy-refactor/phase-02/notes.md`
- `docs/plans/profile-strategy-refactor/phase-02/journal.md`

## Done When
- Multi-level chains resolve independent of declaration order.
- Child workflow selections replace the parent's whole selection.
- Unknown parents and cycles raise clear errors.
- A consult-only profile loads successfully.
- An unmapped workflow fails only during execution-plan resolution.
- Project profiles replace same-name base profiles.
- Project inheritance resolves across the merged namespace.
- Project `X` extending `X` inherits the shadowed base `X`.
- Config writing preserves the reserved `extends` key.
- `python -m pytest tests/test_config.py tests/test_planning.py`
- `python -m pytest`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
