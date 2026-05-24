# phase-3.task-3

## Decisions made (not in spec)
- Rewrote `pyproject.toml` to restore valid TOML while adding `[project.optional-dependencies].dev`.

## Spec deviations
- none

## Tradeoffs accepted
- `pytest-asyncio` resolved to a newer compatible release (`1.3.0`) while satisfying the declared minimum `>=0.23`.

## Assumptions
- `.venv/Scripts/python.exe` is the authoritative interpreter for this repo's validation workflow.

## Follow-ups for human
- none
