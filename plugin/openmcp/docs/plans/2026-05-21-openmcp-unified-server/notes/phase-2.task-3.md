# phase-2.task-3

## Decisions made (not in spec)
- Implemented minimal CLI entrypoint by delegating directly to `server.mcp.run(transport="stdio")`.
- Verified `pyproject.toml` already had `openmcp = "openmcp.cli:main"`, so no metadata edits were needed.

## Spec deviations
- none

## Tradeoffs accepted
- CLI stays intentionally thin and places all tool behavior in server/retry layers for separation of concerns.

## Assumptions
- Existing root `.venv` remains the canonical environment for phase validation commands.

## Follow-ups for human
- none
