# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Use MCP SDK v2 wire-model attributes (`input_schema`, `uri_template`) in the schema tests.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The retained dependency and lock update intentionally make the existing v1 tests RED before the implementation migration.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Before the migration, `uv run pytest tests/test_server.py -q` failed during collection with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`; the updated SDK v2 schema, CLI, lifecycle, and resource-template tests pass.

## Task 2

### Decisions made
- Construct one module-level `MCPServer` and keep transport configuration out of the server settings.
- Add Starlette and Uvicorn as direct runtime dependencies because both are imported by OpenMCP production code.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `MCPServer.streamable_http_app(host=...)` is the SDK v2 public path for host-aware transport security configuration.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: v1 imports and mutable settings failed against the retained SDK v2 lock; the MCPServer import assertion, lock check, and migrated server tests pass.

## Task 3

### Decisions made
- Let the SDK session manager enter the MCPServer lifespan, with the Starlette lifespan only owning the session manager context.
- Resolve host for application transport creation and resolve port only for Uvicorn.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The SDK session manager drains active MCP sessions before its enclosing MCPServer lifespan closes the Runtime.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Former lifecycle tests depended on `_ACTIVE_RUNTIME` and private session-manager seams; public Starlette lifespan tests now verify one Runtime create/start/close sequence and cleanup on start/close failures.

## Task 4

### Decisions made
- Convert the three runtime-backed static resources to optional-query URI templates (`scope` defaulting to the empty string), allowing v2 Context injection while preserving reads at the original exact URIs.

### Spec deviations
- none

### Tradeoffs accepted
- Template listings expose these three entries through `resources/templates` rather than `resources/list`, as required by SDK v2 Context rules.

### Assumptions
- The optional query parameter is compatibility scaffolding and does not change resource contents.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: v1 `inputSchema` assertions and private lifecycle seams failed under SDK v2; tests now use v2 model attributes and public template/lifecycle behavior, with `uv run pytest tests/test_server.py -q` passing 16 tests.
