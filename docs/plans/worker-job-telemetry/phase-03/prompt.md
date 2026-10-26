## User Request
Finish the approved worker-job-telemetry plan. Preserve execution transports and expose trustworthy context and consumption separately.

## Phase
Phase 3: Bounded session telemetry and capability evidence.

## Read First
- /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/DESIGN.md
- /home/ngosi/projects/refract/docs/plans/worker-job-telemetry/PLAN.md, including Shared Contract and Boundaries and all Phase 3 requirements, acceptance criteria and reviewer checklist.
- server/src/refract/backends/codex.py
- server/src/refract/telemetry.py

## Tasks
- task-1: Verify installed CLI versions/interfaces and sanitized session formats through documentation and read-only package inspection. Record evidence and supported measurement limits in server/CLI_ARGUMENTS.md. Do not inspect user conversations or credentials. No live requests are authorized.
- task-2: Add a bounded exact-session Codex rollout collector using verified token_count payload semantics. Prefer event-triggered incremental reads and final reconciliation. Never select an unrelated latest conversation. Safely baseline cumulative counters only in same session/generation or retain invocation-local usage and mark incomplete. Test identity mismatch, concurrent sessions, partial/malformed lines, growth, rotation, truncation, missing files and lifecycle cancellation.
- task-3: Enrich Pi only if verified existing artifacts expose effective capacity. Otherwise retain null and document. Handle explicit Agy context only if evidence supports it. Add offline capability tests and opt-in live probes. Missing prerequisites cannot count as passing probes. Do not run them.

## Context
Phases 1 and 2 implemented persistence and stream usage. Current backend telemetry uses separate reported consumption and derived context observations. Execution assigns actual attempt/invocation identities; backend-local accumulators use local identities. Do not merge context into consumption or double-count final counters. Retain legacy metadata. Keep schema version 15.

## Files
Allowed modifications:
- server/src/refract/backends/codex.py
- server/src/refract/backends/pi.py
- server/src/refract/backends/agy.py
- server/src/refract/backends/_shell.py
- server/src/refract/telemetry.py
- server/tests/test_telemetry.py
- server/tests/test_streaming_backends.py
- server/tests/test_processes.py
- server/tests/test_live_backends.py
- server/CLI_ARGUMENTS.md
- docs/plans/worker-job-telemetry/phase-03/notes.md

## Done When
All Phase 3 acceptance criteria in PLAN.md are satisfied with offline evidence. Reads, discovery, retries and payload sizes have explicit tested bounds. Collectors do not outlive the subprocess or extend deadlines. Compaction/model changes invalidate incompatible context. No guessed capacity, raw payload, sensitive path, user history, extra execution process or transport replacement. Unsupported Pi/Agy capacity stays null. Documentation distinguishes observed, fixture-only and unverified capabilities. Live probes remain unrun without explicit authorization.
- `cd server && uv run pytest` passes.

## Rules
Follow bundled contracts:
- /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- /home/ngosi/projects/refract/plugin/shared/erp.md
- /home/ngosi/projects/refract/plugin/shared/notes-template.md
- /home/ngosi/projects/refract/plugin/shared/journal-template.md

Write focused regression tests first, record exact RED failure and GREEN evidence in notes. Existing behavior changes require characterization coverage. Do not commit, stash, reset or perform Git writes. Coordinator owns Git. Do not edit coordination files other than append notes. Touch only allowed files; request clarification before expanding scope. No live model requests, credential reads, global config edits or user conversation inspection. Read installed Pi docs fully if investigating Pi SDK/session behavior, following relevant cross-references. Use current library/CLI documentation where needed. Keep changes minimal.

## Response Format
Return ERP `# EXTERNAL RESPONSE` and matching status line. Include FILES MODIFIED, capability limitations, test evidence and NEXT.
