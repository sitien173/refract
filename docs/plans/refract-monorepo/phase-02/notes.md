<!-- ccg-shared-version: 12.0.0 -->

# Phase 2: Decision Notes

## Task 1

### Decisions made
- Renamed the package directory with `git mv` and refreshed the lock after changing the distribution metadata.
- Kept dependency versions unchanged; the `uv.lock` delta only replaces the editable project entry with `refract` 1.0.0.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Passing characterization before edits: `cd server && uv sync --all-extras && uv run pytest` — 546 passed, 3 deselected; `cd server/web && npm test` — 203 passed.
- `uv lock` resolved 49 packages; `uv sync --all-extras` reinstalled `refract==1.0.0`.

## Task 2

### Decisions made
- Applied only names/path/header substitutions to server tests, preserving the suite and its assertions; the version smoke assertion now expects 1.0.0.
- Renamed the MCP server error class and app-state dashboard attribute while preserving tools, routes, and behavior.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `cd server && uv sync --all-extras && uv run pytest` — 546 passed, 3 deselected (same baseline count).
- With `REFRACT_HOME` unset and `OPENMCP_HOME` set to an unrelated path, direct `refract_home()` evaluation returned `/home/ngosi/.refract`.

## Task 3

### Decisions made
- Regenerated the npm lock with `npm install` and static assets with `npm run build`; no dependency versions changed.
- Coordinated server/client CSRF header rename to `X-Refract-CSRF` without changing security conditions or routes.

### Spec deviations
- none

### Tradeoffs accepted
- `npm install` reported existing dependency audit advisories; no audit fix or dependency upgrade was performed.

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Passing characterization before edits: `cd server/web && npm test` — 203 passed.
- `cd server/web && npm test` after rename — 203 passed, 18 test files.
- `cd server/web && npm run build` regenerated `server/src/refract/dashboard_static/` with the Refract title and new hashed bundle.

## Task 4

### Decisions made
- Updated server docs with Refract names, CLI commands, state/config paths, environment variables, 1.0.0, and repository URL.
- Fixed all three README diagram link prefixes to `../docs/diagrams/` while retaining the three `openmcp_*` filenames for Phase 3.

### Spec deviations
- none; the three diagram filename matches are the explicitly authorized Phase 3 deferral.

### Tradeoffs accepted
- The three existing diagram filenames remain old until the Phase 3 diagram rename; their relative links are now correct.

### Assumptions
- none

### Follow-ups for human
- Phase 3 should rename and re-export `openmcp_system_architecture.drawio.png`, `openmcp_c4_model.svg`, and `openmcp_data_flow_diagram.drawio.png`, then update their README links.

### Test evidence
- `cd server && uv build` succeeded; source and wheel artifacts are version 1.0.0.
- `cd server && uv run refract --help` succeeded and reports the renamed CLI.
- Case-insensitive residual search excluding caches found exactly the three deferred README diagram targets and no other product-name matches.
- `server/src/openmcp` is absent; no old `OPENMCP_HOME`, `OPENMCP_LOG_*`, or old helper reads remain.
