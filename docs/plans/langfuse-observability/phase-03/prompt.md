## User Request
Implement Phase 3 of the confirmed langfuse-observability plan. Parent goal mvrrr42k-hgscwh is confirmed and active.

## Phase
MCP tool spans and operator documentation.

## Tasks
1. In _logged_request at server/src/refract/server.py:496, record a tool span named after the operation with tool arguments as input, response as output, and outcome, error_type, and duration_ms as metadata. Use trace_id_for_job when the call has a job_id argument or job_submit returns a job ID; otherwise use a standalone trace with session_id = project_id when known. The span covers only the actual request duration.
2. Document the [langfuse] section, the LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY variables, pip install 'refract[langfuse]' or uv sync --extra langfuse, and a warning that prompt and result text, including any repository code or secrets in them, are uploaded to the Langfuse server. Add an Unreleased entry to CHANGELOG.md.

## Context
- Read ../DESIGN.md and ../PLAN.md. Implement only Phase 3.
- Phase 1 supplies the optional per-runtime Tracer holder. Phase 2 supplies job/generation/event helpers. Preserve their behavior.
- `_logged_request` receives both positional and keyword arguments. Preserve wrapped function signatures, returned strings, existing error conversions, and request logging.
- Job identity for job_submit is available only after its response. Record request timestamps without leaving an active observation across a long poll. Verify explicit start/end timestamp APIs against installed SDK source before using them.
- Use the actual per-runtime tracer, including replacements after configuration reload. Do not create a separate client or use global OpenTelemetry state.

## Files
- server/src/refract/observability.py
- server/src/refract/server.py
- server/tests/test_observability.py
- server/tests/test_server.py
- server/README.md
- CHANGELOG.md
- docs/plans/langfuse-observability/phase-03/notes.md
- docs/plans/langfuse-observability/phase-03/journal.md

## Done When
- In-memory exporter integration: job_submit and job_wait yield tool observations on their deterministic job trace.
- project_resolve and task_guide produce standalone traces, using project session identity when known.
- Raised errors produce observations with error_type without changing MCP error responses.
- Tracing failures do not alter tool outcomes. Inactive tracing preserves response/error envelopes and logging.
- No observation stays active during a job_wait long poll. Recorded timestamps cover actual request duration.
- README documents all configuration fields, environment credentials, optional installation, and unredacted content-upload risks. CHANGELOG has an Unreleased entry.
- From server/: `uv run --exact pytest -q`
- From server/: `UV_PROJECT_ENVIRONMENT=/tmp/refract-langfuse-sdk-acceptance uv run --extra langfuse pytest -q`

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Use behavioral TDD. Record genuine assertion failures before production changes, not missing imports or absent helpers.
- Verify SDK APIs using installed SDK source and current documentation. Use only an in-memory exporter and synthetic keys during tests.
- Never read or modify credentials, .env files, daemon home configuration, or ~/.config.
- No unrelated refactors, new dependencies, commits, branches, resets, or pushes.
- Do not modify PLAN.md, DESIGN.md, .handover.md, or prior phase artifacts.
- The coordinator already owns the active parent goal. Do not create a worker-local goal or request goal focus.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
