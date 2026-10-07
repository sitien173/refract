<!-- ccg-shared-version: 11.0.6 -->

# Phase 4 Journal: MCP v2 tool surface

## META

- Plan: docs/plans/mcp-v2-claude-code/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult
- Review Profile: review
- Consultation Job: 944810ff-2093-41f0-acfc-e644f4d5dedd
- Implementation Job: pending
- Review Job: pending
- Started: 2026-10-07
- Finished: pending

## Setup and Guidance

- Pre-phase root: attached main, clean at 03ce218b0ae904808adc3db5db9e668a00436e4b. Plan tracking is tracked. Plan base 491e043dedc0263900e137f9a85fbf781e00530f and Phase 3 impl 1dab467c7a01c5386b3222225e4a87a30116f1ac resolve. Phase 3 DONE, Spec and Quality PASS, no debt.
- No active or queued job. Daemon remains running on reviewed Phase 1 code; no restart before Phase 7.
- task_guide called once for Phase 4. V1 accepts only project_id; complete phase request is PLAN.md Phase 4 Task Guide Input and prompt.md.
- Selected and validated routes: consult/consult for SDK behavior and size-policy analysis, implement/implement for the server/runtime contract, review/review for independent quality. Current profile catalog and built-in workflows contain all three.
- Consultation is required: actual SDK error delivery contradicts a design assumption; fixed character pages and unbounded metadata conflict with the response bound.
- Questions permitting only the matching uv.lock OpenMCP version update received no user answer. No scope approval is recorded. Preserve the lockfile until the Coordinator resolves the omitted path.
- User's existing continued-normal-wait approval applies. No polling or duplicate wait while a wait is in flight. No live configuration/database/authentication/session reads or daemon restart.

## Consultation

- Job 944810ff-2093-41f0-acfc-e644f4d5dedd succeeded with NEXT BLOCKED. No implementation was authorized or performed. Read-only reconciliation passed at 3b21a96fb5617f743236781420224e4d30d5f94e: only the coordinator's handover job reference differs. No active project job. Daemon PID 482030 and startup Wed 2026-10-07 14:01:37 +07 unchanged.
- Minimum SDK approach: OpenMCPError subclasses ToolError; unexpected handler exceptions become sanitized request-ID internal_error; cancellation propagates unchanged; raw tools/call middleware handles validation and normalizes only recognizable OpenMCP JSON suffixes from SDK error prefixes. All seven tools disable structured output and emit one compact JSON text content. Verify the same client regressions under the existing SDK 2.0.0 and 2.3.0 environments without changing either environment or dependency versions.
- Confirmed design conflict: malformed, missing, or out-of-range arguments have no applicable documented error code. internal_error would misclassify caller error; protocol INVALID_PARAMS would be an exception to the model-visible JSON rule. Consultation recommends a documented invalid_request code with schema-correction next_action and retryable=false.
- Confirmed size conflict: fixed 24000-code-point pages can exceed 30000 serialized characters after escaping. Treat 24000 as the maximum candidate page and shrink against the complete serialized response, preserving exact Unicode code-point offsets. A nonterminal timeout_s=0 call is an immediate read with empty result text and no offset advancement.
- Unbounded active jobs, guidance, dependency and cancellation arrays, and user-derived summary strings cannot fit an unconditional response bound under fixed unpaged shapes. Consultation recommends explicit paging where reconciliation must remain complete; an alternative minimum change is a documented response_too_large error with no silent truncation. A conservative serialized byte budget was offered in the user question to address the token-bound requirement without adding a tokenizer dependency. Neither policy is approved.
- The only newly necessary Phase 4 implementation path is uv.lock, limited to the editable OpenMCP package version metadata from 1.2.0 to 2.0.0. No dependency re-resolution or upgrade is warranted. Questions permitting that edit remain unanswered.
- backend_runner.py can be deleted after the server.run facade and its deliberately obsolete tests are removed or replaced. Execution currently converts job IDs to resource URIs solely for notification, and Runtime strips them again before desktop lookup. Pass job IDs directly; keep the desktop consumer and tests/test_notifications.py unchanged. No dashboard source is needed in Phase 4.
- Required additional regressions: every model-visible error code; pre-validation errors; sanitized internal errors; cancellation propagation; recognizable SDK-prefix normalization; no structured duplicate; escaped and non-ASCII exact paging; complete response bound; approved overflow behavior.
- Three bounded decision groups were presented with AskUserQuestion after consultation: argument-error policy, bounded-output policy, and necessary file-scope additions. No user response arrived. A timed-out question is not approval. Handover is BLOCKED; no Phase 4 base or implementation checkpoint exists.

## Related Scope Preflight

- Completed read-only semantic retrieval confirms Phase 5 project-job response changes also require web/src/screens/Projects.jsx and its matching test. That caller is absent from the declared Phase 5 Files list. The bounded scope question also received no answer.
- Dashboard /status and /overview are distinct resources with separate live frontend consumers; do not remove either as an alias. /configuration and /config share a handler; the client uses /configuration. Project /profile-overrides and /configuration/profiles are aliases; the client uses /profile-overrides. Keep client-used paths if approved Phase 5 proceeds.
- Reuse _dashboard_job, runtime.waiting_metadata, database.dependencies_for_job, and the shared JobDetails. Effective reader capacity is scheduler.max_project_readers; reloaded catalog values may be pending, so do not report catalog values as already effective.
- Phase 7 read-only documentation research verifies fresh print-mode stream-json output, verbose, no-session-persistence, and forwarding subagent text. Tool approvals do not create availability. Optional PostToolUse duration_ms may supplement daemon request timestamps; whole-session elapsed time is not six-minute tool-call evidence. Existing Phase 1 evidence requires a 450-second or longer probe timer. No fresh session or probe was run in Phase 4.

## User Approval and Finalized Gate 1

- The final AskUserQuestion was answered: Can I apply the recorded recommendations and continue the remaining phases? Answer: Approve recommendations (Recommended). This is an explicit user selection, unlike earlier timed-out questions or automated feedback.
- Approved: invalid_request JSON schema errors; adaptive result pages and explicit response_too_large for unpageable metadata; only the editable OpenMCP uv.lock version sync; Phase 5 Projects.jsx and its matching test. No list/guidance paging, dependency upgrade, or live configuration change.
- DESIGN.md, PLAN.md, and the Phase 4 prompt now record the chosen contract and exact file scope. The conservative complete-response budget is below 9000 UTF-8 bytes and 30000 characters, with at most 24000 code points in a candidate result page. Oversized unpageable metadata is an explicit error; overflow after a mutation must identify that applied outcome and retain the root ID.
- Fresh reconciliation after approval: main is attached and clean at c39c1883a9d098eeaa3fdde02b08c30c936bccfe; no active project job; plan base and Phase 3 impl resolve. Daemon PID 482030 and startup Wed 2026-10-07 14:01:37 +07 unchanged. The earlier block is resolved. Phase 4 guidance remains the saved consult/implement/review routes and is not re-requested.
- Checkpoint the final coordination files and anchor Phase 4 before implementation. Worker still owns only the declared source/test paths and phase notes/journal.

## Implementation Response

Pending.

## Quality Review

Pending.

## Review Result

- Spec Status: PENDING
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-04/base, pending until finalized consultation and prompt
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-04/impl, pending
- Plan commit ref: pending
- State checkpoint: final Gate 1 contract and scope approved; pending Phase 4 base anchor and implementation
