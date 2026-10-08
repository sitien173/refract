# Phase 7: Live cutover and acceptance

## META

- Plan: mcp-v2-claude-code.
- Coordinator-only phase. No implementation or review job is authorized.
- Primary preflight: clean attached main at 1accfb0c9ccd7da1662c02285dafaad7bd3ee745.
- Companion: clean attached main at reviewed fe7fee0fb68d6f26b76827f2995b134117c318e6.
- Phase6 Coordinator Spec PASS and independent Quality PASS_WITH_DEBT. Q1 LOW test-quality owner: Phase 6 implementer. Preserve this debt.
- Pre-cutover service: active, MainPID482030, started Wed 2026-10-07 14:01:37 +07. No restart since Phase1.
- Daemon preflight: active_jobs0 and queued_jobs0. No wait remains active.

## Confirmed Scope and Procedure

Only this journal and the primary handover are Phase7 coordination changes. All harnesses, temporary MCP configuration, invocation hooks, agent definitions and private raw evidence stay outside implementation roots. No production source edit, dependency/environment upgrade, global configuration change, persistent permission change, Git operation by a worker, or remote publication.

1. Checkpoint these allowed files and set the primary Phase7 base anchor at a clean root.
2. With no active job, run systemctl --user restart openmcp.service. Record a changed process/start time and active state. Parent legacy tool definitions are stale afterwards; do not call removed status/registration/resource tools.
3. Verify the reviewed seven-tool daemon through an actual SDK connection, then discover exact native tools from a fresh Claude Code invocation loading the local v12 plugin and an explicit temporary loopback MCP configuration. Do not infer tool availability from permission approval.
4. Run native main and native custom-subagent job_wait calls. Each must actually execute for at least360seconds and return a terminal, successful tool result. The job itself may be terminally failed only in separate dependency/error fixtures; timer waits must complete successfully. Whole CLI/session elapsed time does not prove duration.
5. Use existing server mcp.request_started/mcp.request_finished records for monotonic duration_ms and progress_token_present; correlate privately with native tool hooks. Never publish a raw progress token, native session/agent/tool-use identity, provider routing or raw stream metadata. Raw files have private permissions.
6. Record the four-call standard cycle and bounded public tool results. Inspect annotations, descriptions/instructions, error action and privacy. Use isolated actual-client tests for disruptive error families instead of corrupting live configuration or stopping the daemon to force errors. Run safe live invalid calls after cutover.
7. Demonstrate dependent cancellation through a controlled fixture without changing live routing or failing an unrelated real job. Record live or isolated evidence distinctly.
8. Run every declared verification command fresh, inspect scope and root state, review the evidence against every criterion, close Phase7 and then consolidate both roots with recovery anchors retained.

## Acceptance Matrix

Source: DESIGN.md:19-27 and PLAN.md:421-450. Every status below is PENDING until evidence is recorded.

| ID | Approved criterion | Planned proof | Status |
|---|---|---|---|
| a | Main or subagent job_wait supports up to3600seconds without a client timeout; after daemon restart the client issues a new wait | Fresh native main and native subagent waits each at least360seconds, server duration/progress presence and terminal return; configured3600 limit and tests. Do not claim an hour was exercised. | PENDING |
| b | Instructions and every description at most2048characters, key facts first | Restarted daemon inventory and actual-client characterization | PENDING |
| c | Resolve, guide, submit, wait and result require at most4calls without a hidden URI | Native terminal one-page standard cycle, exactly four MCP calls | PENDING |
| d | No MCP output exposes execution target/backend/model/provider identity | Restarted native/SDK public outputs, actual-client recursive/privacy and diagnostic regressions | PENDING |
| e | Every error names the next action | All thirteen approved families through isolated actual clients; safe live invalid calls; parseable JSON and next_action | PENDING |
| f | Every tool has accurate annotations | Restarted seven-tool inventory compared with DESIGN.md:74-82 and existing annotation assertions | PENDING |
| g | Every MCP response under10k tokens | Complete serialized responses below30000characters and9000UTF-8bytes with adaptive paging/full reconstruction and explicit metadata overflow. This is conservative headroom, not a measured tokenizer claim. | PENDING |

Additional adopted dependency/admission behavior uses reviewed scheduler/runtime/execution regressions plus the controlled cancellation fixture. Main/subagent native timing and restarted-daemon evidence remain mandatory; tests alone cannot close this phase.

## CLI Evidence Preparation

Verified installed CLI: 2.1.293. Documentation-only preparation is /tmp/mcp-v2-phase7-docs-20261008-085455/phase7-preparation.md. Private prepared hook recorder: /tmp/mcp-v2-phase7-hook.XWsPWE/record-hook.py. These are preparation, not live evidence. Verified hook fields are tool_use_id/tool_response and optional duration_ms; actor attribution uses agent_id presence without retaining its value. Retain foreground waits with CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0 and leave CLAUDE_AUTO_BACKGROUND_TASKS absent in child invocations. Do not infer a need to unset CLAUDECODE. Use only installed verified flags and discovered exact tool names. Keep existing deny rules intact.

## Verification Checks

- systemctl --user is-active openmcp.service.
- uv run --extra dev pytest -q.
- npm --prefix web test.
- git diff --check and unchanged reviewed source in both roots.
- Native wait/result evidence and criterion-by-criterion review.

## Review Result

Spec: PENDING. Evidence quality: PENDING. Live cutover: NOT RUN. Final consolidation: NOT RUN.

## Known Scope Exclusion

The v1 names in docs/diagrams/openmcp_c4_model.drawio and .svg remain outside this confirmed plan. Do not modify them. Preserve recorded intermittent frontend baseline/review failures from Phase5; a later recurrence is a new recorded failure, not permission to rerun silently until green.
