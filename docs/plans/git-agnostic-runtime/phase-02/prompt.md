## Original User Request
Finalize the `git-agnostic-runtime` folder plan.

## Phase
Remove commit messages and workflow write distinctions.

## Tasks
- task-1: Remove `WorkflowDefinition.writes` and simplify request validation.
- task-2: Remove `commit_message` from runtime and database submission APIs.
- task-3: Remove `commit_message` from the public MCP tool.
- task-4: Update affected workflow, server, and execution tests.
- task-5: Update public tool documentation and database-default coverage.

## Context
Keep the physical `jobs.commit_message` column during this phase. Its default
remains empty. Phase 3 removes that column and the remaining Git fields.

## Files
- `src/openmcp/workflows.py`
- `src/openmcp/runtime.py`
- `src/openmcp/server.py`
- `src/openmcp/database.py`
- `tests/test_workflows.py`
- `tests/test_server.py`
- `tests/test_execution.py`
- `tests/test_database.py`
- `README.md`

## Done When
- All three workflows submit using only a prompt.
- Empty or whitespace prompts remain rejected.
- Public and internal submission signatures omit `commit_message`.
- `WorkflowDefinition` exposes no `writes` attribute.
- The jobs insert omits `commit_message` and uses its default.
- MCP schema properties exclude `commit_message`.
- Public examples describe directory registration and prompt-only submission.
- `uv run python -m pytest tests/test_workflows.py tests/test_server.py tests/test_smoke.py tests/test_execution.py tests/test_database.py`
- `tgrep -n "\\.writes|commit_message" src/openmcp`
- Search output contains only Phase 3 schema, detection, and migration references.

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.
Keep schema version 5 and all physical Git columns. Keep legacy migration
extraction of historical commit messages. Do not change model fields, workflow
names, capabilities, profile routing, or target policy.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
