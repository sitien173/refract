## User Request
Implement Phase 2 of the confirmed langfuse-observability plan. Parent goal mvrrr42k-hgscwh is confirmed and active. This is bounded delegated implementation, not a separate persistent goal.

## Phase
Job, attempt, and worker-question tracing.

## Tasks
1. Emit one agent observation named job per executing job, with deterministic trace_id_for_job(job_id), session_id project_id:context_key, prompt input, result text output, workflow/profile/final-state/failure.kind metadata. Failed jobs have ERROR level. Cancelled jobs have WARNING level and status_message cancelled.
2. Emit a generation child per target attempt. Include target model, effective prompt, output, available attempt-local usage, target ID, backend and actual persisted attempt number. Retries must be siblings, not nested. Distinguish target attempts from session-recovery invocations. Finish every observation, including cancellation/error paths.
3. Emit question and answer events on the job trace when AskRegistry publishes a real question or successfully delivers an answer.

## Context
Read docs/plans/langfuse-observability/DESIGN.md, PLAN.md and phase-01/journal.md. Read /tmp/refract-langfuse-phase2-integration-hints.md. Current SDK 4.18.0 source is /tmp/refract-langfuse-sdk-acceptance/lib/python3.12/site-packages/langfuse. Verify signatures there. The runtime owns a replaceable per-runtime Tracer. Do not introduce a cross-runtime global client or mutate the global OpenTelemetry provider. Minimal callback wiring in runtime.py is allowed solely to expose that existing holder to execution and ask hooks.

## Files
- server/src/refract/observability.py
- server/src/refract/execution.py
- server/src/refract/ask.py
- server/src/refract/runtime.py, minimal holder injection only
- server/tests/test_observability.py
- server/tests/test_execution.py
- docs/plans/langfuse-observability/phase-02/notes.md
- docs/plans/langfuse-observability/phase-02/journal.md

## Done When
- Real in-memory exporter integration proves successful job agent and generation identity, parent relationship, input/output/model/usage attributes.
- Retry integration proves sibling generations with attempt-local usage, not repeated job totals.
- Cancellation produces WARNING and cancelled status.
- Questions and answers produce two events with text on the same job trace.
- Unavailable measurements are omitted, including cache values. Installed SDK usage_details accepts arbitrary Dict[str,int]; verified SDK cache names are input_cached_tokens and cache_creation_input_tokens. Canonical telemetry input includes cache counts; avoid double-counting when emitting exclusive usage categories.
- Exceptions at observability helper SDK boundaries do not change job state, output, cancellation or answers.
- Inactive execution tests still pass.
- From server/: uv run --exact pytest -q
- From server/: UV_PROJECT_ENVIRONMENT=/tmp/refract-langfuse-sdk-acceptance uv run --extra langfuse pytest -q tests/test_observability.py tests/test_execution.py tests/test_ask.py
- Full suites take about 204 seconds. Use a 1200-second command bound, not 180 seconds.

## Rules
Follow /home/ngosi/projects/refract/plugin/shared/worker-contract.md, erp.md, notes-template.md and journal-template.md.
Use behavioral TDD. Import failures do not count as RED. Start from integration assertions that execute successfully before failing for absent spans. Keep all SDK imports in observability.py and optional SDK test paths. No exporter network activity in tests. Each public observability helper catches Exception, warns once with event langfuse.error, and returns without changing caller behavior. Hook code stays limited to observability calls. Never read credentials, .env*, ~/.config or daemon home configuration. Credentials only through LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY. No Git changes. No adjacent refactors. Do not change PLAN.md, DESIGN.md or .handover.md. Record actual RED and GREEN evidence and append the ERP response to the journal.

## Response Format
Return # EXTERNAL RESPONSE and the matching Phase 2 status line required by erp.md.
