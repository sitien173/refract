## Original User Request

Remove redundant target capabilities. Keep fixed workflow names.

## Phase

Simplify core workflow and target routing.

## Tasks

- task-1: Replace workflow definitions with validated strings.
- task-2: Remove capabilities from target configuration.
- task-3: Remove capabilities from new plan snapshots.
- task-4: Reject unknown profile workflow keys.

## Context

`workflows.py` currently models names and capabilities together. Profiles already
select targets directly. `planning.py` snapshots complete target configuration.
Old snapshots containing capability fields must remain parseable. Workflow names
remain durable context roles and public MCP values.

Use test-first coverage for unknown profile keys. Preserve passing
characterization coverage for routing and legacy plan parsing. Do not change
public target response models or dashboard files during this phase. Do not add
dynamic workflows or the separate job-plan workflow invariant.

## Files

- `src/openmcp/workflows.py`
- `src/openmcp/config.py`
- `src/openmcp/planning.py`
- `src/openmcp/runtime.py`
- `tests/test_workflows.py`
- `tests/test_config.py`
- `tests/test_planning.py`
- `tests/test_execution.py`
- `tests/orchestration_helpers.py`
- `docs/plans/workflow-capability-simplification/phase-01/notes.md`
- `docs/plans/workflow-capability-simplification/phase-01/journal.md`

## Done When

- Fixed workflow names remain unchanged.
- Unknown submissions remain rejected.
- Unknown profile workflow keys fail loading.
- Built-in workflows still resolve configured targets.
- New plans omit capabilities.
- Legacy plans containing capabilities still parse.
- Target selection and retries remain unchanged.
- `uv run pytest tests/test_workflows.py tests/test_config.py tests/test_planning.py tests/test_execution.py`
- `tgrep -n "WorkflowDefinition|_BUILTIN_WORKFLOW_CAPABILITIES|capabilities" src/openmcp/workflows.py src/openmcp/config.py src/openmcp/planning.py src/openmcp/runtime.py`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
