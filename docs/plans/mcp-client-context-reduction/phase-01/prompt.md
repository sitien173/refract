## Original User Request
Ship backlog item B-003.

## Phase
Bound the jobs resource and prune MCP resources.

## Tasks
- task-1: Remove five obsolete resource endpoints only.
- task-2: Add and export the slim `JobSummary` model.
- task-3: Return bounded active, recent, and truncated jobs.
- task-4: Update tests for payload and templates.

## Context
The full design and exact requirements live in `../PLAN.md` Phase 1 and `../DESIGN.md`. Preserve full database job rows. Keep full single-job results. Active jobs remain uncapped. Recent terminal jobs cap at ten, sorted by `updated_at` descending.

## Files
- `src/openmcp/server.py`
- `src/openmcp/models.py`
- `tests/test_server.py`

## Done When
- Exactly six resource templates remain.
- The jobs resource returns `active`, `recent`, and `truncated`.
- The busiest project payload remains under 4 KB.
- No list item contains `result`.
- The single-job resource retains full `result.text`.
- `uv sync --all-extras --frozen`
- `uv run pytest`
- `uv build`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
