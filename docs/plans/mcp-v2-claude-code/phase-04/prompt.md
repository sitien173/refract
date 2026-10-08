# Phase 4: MCP v2 tool surface

## User Request

Complete mcp-v2-claude-code. Replace the v1 MCP surface with the confirmed seven-tool contract, preserve durable jobs and reviewed dependency scheduling, and keep the running daemon unchanged until Phase 7.

## Status

Finalized after read-only consultation and the user's explicit approval of the four recorded recommendations. Implement Phase 4 only. The unanswered earlier questions were not approval; the final approval question was answered Approve recommendations.

## Tasks

- task-1: Add compact JSON OpenMCPError using SDK ToolError, the design's codes including invalid_request and response_too_large, and next_action. Map expected runtime errors, cover pre-handler validation, and sanitize unexpected exceptions with the request ID.
- task-2: Implement project_resolve, task_guide, job_submit, job_wait, job_list, job_cancel, and job_retry with the confirmed parameters, shapes, titles, annotations, instructions, and server title.
- task-3: Resolve canonical directories idempotently, handle alias collisions and concurrent insertion, expose immutable dependency/admission metadata, bound terminal listings, and page terminal results without losing text under the serialized response budget.
- task-4: Remove the v1 MCP tools/resources/subscriptions, resource URI fields/helpers, and direct-run facade. Key runtime notifications by job ID, retain desktop notifications, bump OpenMCP to 2.0.0 with its matching lockfile metadata, and update relevant README statements.

## Context

- Read /home/ngosi/projects/openmcp/docs/plans/mcp-v2-claude-code/PLAN.md Phase 4 and DESIGN.md. Phases 1 to 3 passed specification and independent quality review. Phase 3 final ref is refs/plans/mcp-v2-claude-code/phase-03/impl. Reuse the existing heartbeat, immutable dependency APIs, access classes, waiting_metadata, and generation-safe scheduler. Do not refactor reviewed scheduling or change Phase 2 persistence/configuration.
- Existing project and job IDs remain valid. The public summary has exactly the design fields; do not serialize a full internal JobView. Exclude target_id, backend, model, resource_uri, and config_revision recursively from all tool payloads. Dashboard internals retain operator detail. Expected and unexpected MCP errors must not reveal provider detail or stack traces.
- Every parameter has a description; workflow is the four-value enum, timeout_s ranges from 0 to 3600, and result_offset is nonnegative. timeout_s=0 is an immediate read. Descriptions and instructions are at most 2048 characters and instructions name every tool. Preserve the design's accurate annotations and server title.
- Official SDK docs confirm generic exceptions hide messages. OpenMCPError subclasses mcp.server.mcpserver.exceptions.ToolError. MCPError is a protocol exception, not the required model-visible isError. Register all seven tools with structured_output=False and emit one compact JSON text content rather than a pretty-serialized BaseModel or a duplicated structured response.
- Current docs: https://py.sdk.modelcontextprotocol.io/v2/servers/handling-errors and https://py.sdk.modelcontextprotocol.io/v2/servers/structured-output. https://py.sdk.modelcontextprotocol.io/advanced/middleware documents raw ctx.params before validation and call_next(ctx) performing validation/dispatch. The installed SDK has public MCPServer middleware and server.middleware. Verify exact interfaces rather than guessing.
- Consultation recommends a single tools/call middleware: cover recognizable pre-handler argument validation failures with invalid_request, normalize only a recognizable OpenMCP JSON payload from the SDK error prefix, and ensure unexpected failures become sanitized internal_error. Never strip arbitrary error strings. Pass OpenMCPError through; propagate asyncio.CancelledError unchanged. Avoid duplicate competing error pipelines.
- Error payload is one pure compact JSON object with code, message, next_action, retryable and isError at the MCP result level. invalid_request is retryable=false and tells the caller to correct arguments against the tool schema. response_too_large is explicit and never masquerades as an ordinary success. Keep every other documented code and next action.
- The locked test SDK is 2.0.0 and live pipx SDK is 2.3.0. Verify isolated actual-client error and middleware regressions under both existing interpreters. Do not change either environment, dependency versions, or global configuration. If an interpreter or capability is unavailable, report exactly what was not checked instead of claiming compatibility.
- Database.projects returns stored roots/aliases; Database.project accepts ID or alias; Database.jobs returns full views. Reuse the existing APIs and root uniqueness constraint. Do not add database.py to scope. A concurrent root-insertion loser must re-read the existing row; default alias collisions suffix -2, -3, and so on, while a taken explicit alias is alias_taken.
- backend_runner.py has only the server.run facade and its obsolete smoke-test consumers. Delete it only after no import remains. Preserve unrelated adapter/transport characterization coverage while replacing deliberately removed facade tests.
- Execution converts job IDs to URIs solely for notification; Runtime strips them again before desktop lookup. Pass job IDs directly, keep the desktop consumer, and do not change tests/test_notifications.py. Resources and subscriptions are removed rather than re-created as another abstraction.
- Exact search found no shipped sequentially task-guide instruction in src or README. Live external guidance is out of scope. README's affected MCP, commit, admission, and subscription statements need the v2 vocabulary; unrelated examples do not.
- Legacy name removal refers to the MCP surface and its URI/facade helpers. Do not remove unrelated HTTP status endpoints or ordinary status fields. Dashboard vocabulary changes belong to Phase 5.

## Approved Size Policy

- Preserve the seven existing signatures and the fixed success shapes. No list or guidance pagination, new tool, tokenizer dependency, or configurable response limit.
- A complete serialized CallToolResult must be under 30000 characters and under a conservative 9000-byte UTF-8 budget. Measure the actual JSON text-content envelope, including escaping, not only the original Python string. Apply the bound to success and error responses alike.
- 24000 Unicode code points is the maximum candidate result page. Shrink against the actual complete serialized result. Offsets index authoritative text by Unicode code point, and next_offset advances by the actual page length. At EOF it is null. No character may be silently dropped, duplicated, or transformed.
- Page terminal result text only. Nonterminal calls return empty text, do not advance the offset, and return the design's normal next_action on timeout. An immediate terminal read must not wait for scheduler events.
- Unpageable summaries, active lists, arbitrary guidance, dependency/cancellation arrays, and oversized error metadata return response_too_large with actionable next_action rather than silent omission. This can require dashboard intervention before resume reconciliation; the user explicitly chose this minimum policy over additional paging parameters.
- If overflow is detected after submit, retry, cancel, or project resolution already applied, say that the operation applied and preserve the root job or project ID in message/next_action. Do not tell the caller to blindly resubmit. Prefer a pre-mutation check where straightforward; do not add speculative transaction frameworks or change reviewed scheduling.
- Add deterministic ASCII, quotes, backslashes, CR/LF, emoji and other non-ASCII paging tests, exact reassembly/offset tests, and full-envelope byte/character assertions. Cover metadata-only overflow, bounded errors, and applied-mutation overflow semantics.

## Files

Allowed relative to /home/ngosi/projects/openmcp:
- src/openmcp/server.py
- src/openmcp/models.py
- src/openmcp/runtime.py
- src/openmcp/execution.py
- pyproject.toml
- uv.lock, only the editable OpenMCP version metadata from 1.2.0 to 2.0.0; no re-resolution or dependency update
- README.md
- tests/test_server.py
- tests/test_runtime.py
- tests/test_execution.py
- tests/test_smoke.py
- src/openmcp/backend_runner.py, delete only if no imports remain

Worker-owned artifacts:
- docs/plans/mcp-v2-claude-code/phase-04/notes.md
- docs/plans/mcp-v2-claude-code/phase-04/journal.md

All other paths are read-only. The Coordinator owns prompt.md, PLAN.md, DESIGN.md, .handover.md, and Git. Phase 5's approved Projects.jsx change is not part of this implementation job. A necessary additional path is BLOCKED pending scope resolution.

## Done When

- The actual MCP client sees exactly seven tools, accurate titles/annotations, described parameters, correct enum/range constraints, the required instructions/title, and no resource or template.
- In-process resolve, guide, submit, and wait completes in four calls for a result fitting one page. Recursive scans of every tool's success/error output find none of the forbidden identity or resource keys.
- Canonical path, symlink, alias collision, and concurrent resolve tests pass. Terminal cancel returns an unchanged summary. Unknown IDs, every documented expected error family, schema validation, and unexpected failures arrive as pure parseable JSON with isError and next_action.
- Heartbeats retain the reviewed raw progress-token presence logging and increasing progress, carry state and waiting_reason, and stop on completion, timeout, or client cancellation without mutating the job.
- Terminal paging reassembles exact text. Complete success/error results respect both approved bounds; oversized non-pageable data is an explicit actionable error. No duplicated structured content.
- Desktop notification tests pass with job-ID keys. No v1 MCP surface, URI helper, subscription machinery, or run facade remains in src or README. No unrelated scheduler, adapter, or dashboard changes.
- Both version records are 2.0.0 and uv.lock dependency records remain unchanged.
- Record regression RED before behavior changes, then fresh GREEN and full verification at the exact working tree. Preserve earlier consultation and approval journal sections; append the full ERP response.
- uv run --extra dev pytest tests/test_server.py tests/test_runtime.py tests/test_execution.py tests/test_smoke.py tests/test_notifications.py -q
- uv run --extra dev pytest -q
- Isolated client error/middleware compatibility checks using the existing SDK 2.0.0 and 2.3.0 environments
- git diff --check

## SKILLS

- test-driven-development: /home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md
- verifying-before-completion: /home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md

## Rules

Follow the existing worker contract and ERP. Read existing files before edits; reuse helpers/conventions; write only required code. No silent scope expansion, dependency changes, speculative API, adjacent cleanup, or provider identity in MCP output.

Use Auggie for semantic retrieval, tgrep for exact search, and Read for supplied paths. Never use native grep/find/ls/Glob/Grep or generic terminal code searches. Library/CLI APIs require current ctx7 documentation; public web only tvly. Never send secrets in queries.

No Git writes, OpenMCP calls, service restart, global configuration change, or live/global configuration/database/authentication/session reads. SDK package imports and service-independent isolated test fixtures are permitted; tests use temporary notification-disabled homes. Maintain notes and append ERP. Stop with BLOCKED on truly unresolved scope or behavior; the previously listed four decisions are now resolved by explicit user approval.

## Response Format

Return # EXTERNAL RESPONSE, actual checks, every modified path, and the matching NEXT/status line. Keep execution identities private.
