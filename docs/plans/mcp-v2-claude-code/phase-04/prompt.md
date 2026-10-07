# Phase 4: MCP v2 tool surface

## User Request

Complete mcp-v2-claude-code. Replace the v1 MCP surface with the confirmed seven-tool contract, preserve durable jobs and reviewed dependency scheduling, and keep the running daemon unchanged until Phase 7.

## Status

Consultation preparation only. Do not implement until the Coordinator finalizes this prompt after consultation and resolves the listed scope and design questions.

## Tasks

- task-1: Add model-visible compact JSON OpenMCPError with the design's codes and next_action; map expected runtime errors and hide unexpected exceptions behind request-ID internal_error.
- task-2: Implement project_resolve, task_guide, job_submit, job_wait, job_list, job_cancel, and job_retry with the confirmed parameters, shapes, titles, annotations, instructions, and server title.
- task-3: Resolve canonical directory identity idempotently, handle alias collisions and concurrent insertion, expose immutable dependency/admission metadata, bound terminal listings, and page terminal results without losing text.
- task-4: Remove all v1 tools/resources/subscriptions, resource URI fields/helpers, and the direct-run facade; key runtime notifications by job ID, retain desktop notifications, bump OpenMCP to 2.0.0, and update the relevant README contract.

## Context

- Read ../PLAN.md Phase 4 and ../DESIGN.md. Phases 1 to 3 passed specification and independent quality review. Phase 3 final ref is refs/plans/mcp-v2-claude-code/phase-03/impl. Reuse the existing heartbeat, immutable dependency APIs, access classes, waiting_metadata, and generation-safe scheduler. Do not refactor reviewed scheduling.
- Existing project and job IDs remain valid. The MCP summary excludes target_id, backend, model, resource_uri, and config_revision. Dashboard internals may retain operator detail.
- Tool descriptions and instructions are at most 2048 characters. Instructions name every tool. Schema describes every parameter; workflow is the four-value enum and timeout_s ranges from 0 to 3600. timeout_s=0 in v2 means an immediate read.
- Official SDK documentation confirms generic exceptions hide messages. OpenMCPError must use the supported model-visible ToolError path. MCPError is a protocol error, not the required isError result. The locked test SDK and live SDK were previously verified as 2.0.0 and 2.3.0; verify compatibility through isolated tests without changing either environment or dependency versions.
- Current docs: https://py.sdk.modelcontextprotocol.io/v2/servers/handling-errors and https://py.sdk.modelcontextprotocol.io/v2/servers/structured-output. ToolError import is mcp.server.mcpserver.exceptions. structured_output=False is supported. Official middleware docs at https://py.sdk.modelcontextprotocol.io/advanced/middleware describe raw ctx.params before validation, server.middleware.append, and call_next(ctx) running validation and handler dispatch. Verify exact installed SDK interfaces rather than guessing.
- Size evidence: a 24000-character ASCII result produces about 24071 characters in one compact JSON envelope; 24000 newline or quote characters produce about 48071. Default structured output duplicates the result. Fixed text length alone cannot satisfy the response bound. Summary strings, dependencies, cancellation lists, task guidance, and the unbounded active list can also exceed it. Consultation must settle the minimum policy before implementation. Never truncate silently or add an undeclared tool.
- Database.projects returns stored roots and aliases. Database.project accepts either ID or alias. Database.jobs returns all full job views; existing helpers may suffice but do not add database paths silently. A root uniqueness constraint settles concurrent resolve calls.
- backend_runner.py currently has only the server facade and legacy smoke tests as exact-search references. The plan permits deletion only after no imports remain. Preserve adapter behavior and unrelated transport coverage; replace only tests of the deliberately removed facade.
- Exact search found no shipped sequentially task-guide instruction in src or README. The live external task guide is configuration, not approved repository scope. Do not edit live configuration.
- README currently has stale commit/FIFO/subscription statements. Update only statements directly affected by this v2 contract, not unrelated configuration examples.

## Files

Allowed production and tests relative to /home/ngosi/projects/openmcp:
- src/openmcp/server.py
- src/openmcp/models.py
- src/openmcp/runtime.py
- src/openmcp/execution.py
- pyproject.toml
- README.md
- tests/test_server.py
- tests/test_runtime.py
- tests/test_execution.py
- tests/test_smoke.py
- src/openmcp/backend_runner.py, delete only if no imports remain

Worker-owned artifacts:
- docs/plans/mcp-v2-claude-code/phase-04/notes.md
- docs/plans/mcp-v2-claude-code/phase-04/journal.md

All other paths are read-only. The Coordinator owns prompt.md, PLAN.md, DESIGN.md, .handover.md, and Git. A necessary extra path is BLOCKED pending scope resolution.

## Open Scope and Design Questions

1. pyproject.toml must become 2.0.0, but uv.lock stores the editable OpenMCP record as 1.2.0 and is omitted from the declared scope. Questions to allow only the matching package version update received no user answer. This is unresolved, not approval. Do not modify uv.lock or let verification commands regenerate it until the Coordinator resolves scope.
2. Determine a size-aware result page policy that preserves every character and valid offsets while keeping the complete serialized response under 30000 characters. The design calls the page size 24000 characters; clarify whether that is a maximum instead of a fixed size. Test escaped strings and non-ASCII text, not just ASCII.
3. Determine behavior when non-pageable metadata alone exceeds the response bound, especially active jobs and arbitrary guidance. Returning all entries, bounding every response, and never silently truncating must remain coherent. Identify any necessary user decision rather than inventing a policy.
4. Determine a minimal structured pre-validation error policy for schema failures and uncaught exceptions without adding undocumented error codes, exposing provider details, or weakening schema enum/range constraints.

## Done When

- The actual MCP client sees exactly seven tools, accurate titles/annotations, described parameters, correct enum/range constraints, the required instructions/title, and no resource or template.
- In-process resolve, guide, submit, and wait completes in four calls. Recursive scans of every tool output find none of the forbidden identity or resource keys.
- Canonical path, symlink, alias collision, and concurrent resolve tests pass. Terminal cancel returns an unchanged summary; unknown IDs and all expected error families are model-visible parseable JSON with next_action.
- Heartbeats retain the reviewed raw progress-token logging and increasing progress, include state and waiting_reason, and terminate on completion, timeout, or client cancellation without mutating the job.
- Terminal paging reassembles exact text; timeout returns the normal next_action. Every complete response is below the agreed bound under the finalized size policy.
- Desktop notification tests pass with job-ID keys. No v1 surface name or URI remains in src or README. No unrelated adapter or scheduler change.
- Record regression RED before behavior changes, then fresh GREEN and full verification at the exact working tree.
- uv run --extra dev pytest tests/test_server.py tests/test_runtime.py tests/test_execution.py tests/test_smoke.py tests/test_notifications.py -q
- uv run --extra dev pytest -q
- git diff --check

## SKILLS

- test-driven-development: /home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md
- verifying-before-completion: /home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md

## Rules

Follow the existing worker contract and ERP. Read existing files before edits; reuse helpers and conventions; write only required code. No silent scope expansion, new dependency, dependency version update, speculative API, adjacent cleanup, or provider identity in MCP output.

Use Auggie for semantic retrieval, tgrep for exact search, and Read for supplied paths. Never use native grep/find/ls/Glob/Grep or generic terminal code searches. Library/CLI APIs require current ctx7 documentation; public web only tvly. Do not send secrets in queries.

No Git writes, OpenMCP calls, service restart, global configuration change, or live/global configuration/database/authentication/session reads. Tests use isolated fixtures and notification-disabled homes. Maintain notes and append the complete ERP. Stop with BLOCKED on unresolved scope or behavior.

## Response Format

Return the ERP # EXTERNAL RESPONSE block, actual checks and every modified path, and matching NEXT status. Keep execution identities private.
