## Original User Request
Complete dashboard target-profile CRUD.

## Phase
Expose protected global target CRUD through dashboard editor APIs.

## Tasks
- Add strict target editor request and response models.
- Implement target TOML creation, update, reference scanning, and deletion through `ConfigurationMutationService`.
- Register protected editor routes and stable error translation.
- Add API security, concurrency, redaction, and compatibility tests.

## Context
Read Phase 2 in `PLAN.md` and the confirmed design. Keep runtime `/dashboard/api/targets` unchanged. Use the Phase 1 mutation service exclusively. Require loopback reads, loopback host/client, matching origin, CSRF, `If-Match`, ETag, and no-store responses.

## Files
- `src/openmcp/config_mutation.py`
- `src/openmcp/models.py`
- `src/openmcp/dashboard.py`
- `tests/test_config_mutation.py`
- `tests/test_dashboard.py`

## Done When
- Complete target CRUD meets every Phase 2 acceptance criterion.
- `uv run pytest tests/test_config_mutation.py tests/test_dashboard.py -q`
- `uv run pytest tests/test_server.py tests/test_runtime.py -q`
- `git diff --check`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
