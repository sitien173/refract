# Phase 2 — Journal: Job, attempt, and worker-question tracing

## META

- Plan: docs/plans/langfuse-observability/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: n/a (explicit delegated implementation request)
- Review Job: n/a
- Started: 2026-10-28T16:51:39+07:00
- Finished: 2026-10-28T17:07:39+07:00

## Quality Review

- Independent read-only review `dca8081049ead9ac3bd881b26c480147c`, pinned `openai-codex/gpt-6.1-sol`, reviewed clean checkpoint `fd8c8f914922e7dc06b66e7614dc728c017679f6`: FAIL.
- P2: manually entered observation contexts can bypass exit on final database-read failure or cancellation during finalization awaits. Protect exits with unconditional outer finally or structured context managers. Add targeted cancellation and final-read-failure regressions.
- P2: loaded output/cache measurements without input are dropped by `_calculate_attempt_totals` fallback. Preserve independently available loaded fields. Add output-only and cache-only regressions.
- Alternate independent route remains authorized after canonical review authentication failure recorded in Phase 1. Review was read-only; HEAD and clean root were unchanged.

## Review Result

- Spec Status: PASS after coordinator corrections and fresh acceptance
- Quality Status: PASS after independent fix-delta re-review `d89fe1b0fde254b1b4bbec10c86907674`
- Debt: none

## Coordinator Specification Corrections

- Implementation job `62ad1973-0071-470d-b7e4-ae6507302642` returned ERP TASK_COMPLETE. The declared file set matched the diff. No source changes were committed by the worker.
- The worker's missing-helper AttributeError is not evidence of the real hook behavior. The coordinator added real runtime assertions rather than relying on direct helper tests.
- Behavioral RED `b69dc9cd3`: the real two-attempt integration failed with missing `langfuse.observation.usage_details`. Root cause: usage was sampled before invoking the driver. Usage calculation now runs inside the guarded observation finish helper, after the attempt. Available per-attempt fields are preserved; cached token categories are subtracted from inclusive canonical input to prevent double-counting.
- Behavioral RED `b78aa63d3`: an unrelated observation inherited `session.id=project:context`. Root cause: propagation was exited before its nested observation. Exit order is now observation then propagation.
- Runtime integration coverage now includes real cancellation level/status and SDK construction-helper exceptions preserving job success and text.
- Fresh focused correction checks `bc027e31c` passed: 19 passed in 8.93s. SDK-present Phase 2 acceptance `b2fe7ab95` passed: 187 passed in 241.93s. SDK-absent full acceptance `bfdb70111` passed: 1207 passed, 13 skipped, 15 deselected in 256.56s. Independent quality review remains pending.

## Coordinator Specification Review

- Success trace identity, prompt/output/model, and child parentage: met by real Runtime integration and in-memory exporter assertions.
- Retry sibling parentage and per-attempt available usage: met by streaming two-attempt integration, including cache exclusivity and absent cache-write omission.
- Cancellation WARNING/cancelled: met by actual Runtime cancellation integration and wrapper test.
- Worker question/answer events: met by real AskRegistry publication/delivery integration; unsuccessful duplicate delivery emits no event.
- Inactive compatibility: met by full SDK-absent suite, including existing execution tests.
- SDK exception isolation: met by actual successful Runtime job under SDK start-helper failure; result text remains unchanged.
- Lazy imports, private provider isolation, and reverse context cleanup: inspected against the exact Phase 2 source diff.
- Scope matches the approved Phase 2 file set. `git diff --check` passed.

## SDK Signature Verification

Inspected the installed SDK from `/tmp/refract-langfuse-sdk-acceptance` (Langfuse 4.18.0). `Langfuse.start_as_current_observation` accepts `trace_context`, `name`, `as_type`, `input`, `model`, `metadata`, and `usage_details`; `usage_details` is `Optional[Dict[str, int]]`. `propagate_attributes` is a top-level SDK context manager accepting `session_id`; it is not a `Langfuse` instance method. `Langfuse.create_event` accepts `trace_context`, `name`, `input`, and metadata/status fields. `LangfuseGeneration.update` and agent update accept output, metadata, level and status message.

Verified in project telemetry source that attempt totals are available from `TelemetryAccumulator._calculate_attempt_totals(attempt)`. On the loaded-state fallback this method can synthesize zeros for unavailable output/cache fields; Phase 2 filters those based on known loaded measurements. SDK-verified cache keys used here are `input_cached_tokens` and `cache_creation_input_tokens`.

## Test and Implementation Evidence

- New in-memory test initially failed behaviorally because `job_observation` was absent (`AttributeError`), then passed after helper implementation.
- The first focused acceptance run had 1 failure in task cancellation: `JobView` exposes `result.text`, not `text`. Fixed the correct lookup; cancellation plus the exporter integration passed.
- Final SDK-present focused command from `server/`: `UV_PROJECT_ENVIRONMENT=/tmp/refract-langfuse-sdk-acceptance uv run --extra langfuse pytest -q tests/test_observability.py tests/test_execution.py tests/test_ask.py` passed: 185 passed in 200.94s.
- Final SDK-absent full command from `server/`: `uv run --exact pytest -q` passed: 1207 passed, 11 skipped, 15 deselected in 203.64s.
- The SDK-present tests use only an in-memory exporter and synthetic test keys; no exporter network activity occurred.
- `git diff --check` passed. No Git changes/checkpoints were created.
- No exporter network activity; test public/secret values are synthetic. No credentials, `.env*`, `~/.config`, or daemon-home config were accessed.

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir: Phase 2 / 2026-10-28T16:51:39+07:00 / 2026-10-28T17:07:39+07:00 / docs/plans/langfuse-observability
## SUMMARY
Implemented job agent, per-target-attempt generation, and AskRegistry question/answer tracing with failure-isolated SDK helpers and in-memory integration coverage.
## FILES MODIFIED
| Action | Path | Change |
| Modify | server/src/refract/observability.py | Added guarded job/generation observations and job events with deterministic job trace identity |
| Modify | server/src/refract/execution.py | Wired job and target-attempt observations, attempt-local available usage, and terminal levels/status |
| Modify | server/src/refract/ask.py | Emitted question and successfully delivered answer events outside the registry lock |
| Modify | server/src/refract/runtime.py | Passed the existing replaceable per-runtime tracer holder to execution and ask hooks |
| Modify | server/tests/test_observability.py | Added real SDK in-memory tests for job/generation parentage, retry siblings, events, and cancellation status |
| Modify | server/tests/test_execution.py | Added Runtime job/generation and real retry sibling exporter integration tests |
| Create | docs/plans/langfuse-observability/phase-02/notes.md | Recorded task decisions and behavioral TDD evidence |
| Create | docs/plans/langfuse-observability/phase-02/journal.md | Recorded SDK signature verification, acceptance evidence, and this ERP |
## NOTES
- phase-02/notes.md (## Task 1, ## Task 2, ## Task 3, ## Acceptance)
## SPEC COMPLIANCE
- Meets Spec? YES — requested acceptance checks passed in SDK-present and SDK-absent environments.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Final Checkpoint

- Phase base ref: n/a (no Git changes authorized)
- Phase implementation ref: n/a (no Git changes authorized)
- Plan commit ref: n/a
- State checkpoint: n/a (no Git changes authorized)

## Review Fix Cycle 1 — Implementation Response

Behavioral RED/GREEN evidence for this cycle:

- RED in-memory usage integration: output-only and cache-only loaded measurements each failed because `langfuse.observation.usage_details` was absent (test assertion at `tests/test_observability.py:132`).
- RED lifecycle integrations retained entered context managers to rule out garbage collection. Final job-read exception left a valid current job span; cancellation during target-attempt finalization emitted no generation. Both failures reproduced before production corrections.
- GREEN: available loaded measurements are exported independently after subtracting already completed attempts. Entered generation/job observations exit from unconditional cleanup, restoring active context and finishing observations through the targeted exception/cancellation paths.
- Final `server/` SDK-absent acceptance: `uv run --exact pytest -q` — 1207 passed, 18 skipped, 15 deselected in 241.88s.
- Final SDK-present acceptance: `UV_PROJECT_ENVIRONMENT=/tmp/refract-langfuse-sdk-acceptance uv run --extra langfuse pytest -q tests/test_observability.py tests/test_execution.py tests/test_ask.py` — 192 passed in 229.12s.
- `git diff --check` passed. No independent review is claimed for this fix cycle.

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir: Phase 2 review fix cycle 1 / 2026-10-28T17:07:39+07:00 / 2026-10-28T17:27:00+07:00 / docs/plans/langfuse-observability
## SUMMARY
Fixed observation cleanup on finalization exceptions/cancellation and preserved independently available loaded output/cache usage with completed-attempt subtraction.
## FILES MODIFIED
| Action | Path | Change |
| Modify | server/src/refract/execution.py | Guaranteed generation and job observation exits through nested finally blocks, including cancellation at finalization awaits |
| Modify | server/src/refract/observability.py | Preserved per-field loaded attempt measurements and subtracted completed-attempt aggregates |
| Modify | server/tests/test_execution.py | Added deterministic cancellation and final database-read exception regressions with retained contexts |
| Modify | server/tests/test_observability.py | Added in-memory output-only and cache-only usage export regressions |
| Modify | docs/plans/langfuse-observability/phase-02/notes.md | Recorded review-fix RED/GREEN evidence and final acceptance results |
| Modify | docs/plans/langfuse-observability/phase-02/journal.md | Appended review-fix evidence and this ERP without replacing coordinator-owned history |
## NOTES
- phase-02/notes.md (## Review Fix Cycle 1 — P2 Observation Finalization and Loaded Telemetry)
## SPEC COMPLIANCE
- Meets Spec? YES — both reported P2 blockers were reproduced behaviorally and corrected; required acceptance suites pass.
## CLARIFICATIONS NEEDED
None
## NEXT
CONTINUE_CONTEXT

## Resume Reconciliation

- Resumed at HEAD `fd8c8f914922e7dc06b66e7614dc728c017679f6` on attached branch `main`.
- No Refract jobs are active. Implementation `056e5c4e-07dd-40ba-872e-3e51b431ce08` owns the pending review-fix changes. Later implementation `70cfd1f3-2228-4bf2-9a18-9701a676cc2a` failed with empty output and retryable=false; it supplies no implementation evidence.
- Handover prematurely selected Phase 3 and claimed Phase 2 reviewed, but Phase 2 has no implementation anchor and its journal still requires fix-delta review. Restored current_phase=2 without altering source changes or completed-phase anchors.
- Fresh coordinator acceptance task `b6e67f48f` passed both specified Phase 2 commands sequentially: SDK-absent full suite 1207 passed, 18 skipped, 15 deselected in 188.97s; SDK-present subset 192 passed in 174.71s. Exit code 0. Source remained unchanged during verification. Phase 3 preparation files remain coordination-only; no Phase 3 implementation has started.
- The pending fix delta contains only the approved Phase 2 production and test paths. `git diff --check` passed.

## Independent Fix-Delta Re-review

- Verified delegate `d89fe1b0fde254b1b4bbec10c86907674`, pinned `openai-codex/gpt-6.1-sol`, returned PASS at clean checkpoint `b0f726d3485e092633c92985b61b97958033db90`.
- Both P2 blockers were resolved. Observation contexts exit during finalization failure/cancellation; independently available loaded usage fields survive with prior-attempt subtraction.
- No new actionable correctness/security defects or debt were found within the fix scope. Reviewer inspected live source and targeted tests, not Git history, and did not execute tests independently.
- Coordinator confirmed unchanged HEAD and clean root after review. Fresh acceptance is recorded above.
- Final Spec Status: PASS. Final Quality Status: PASS. Debt: none.
- Phase implementation anchor: refs/plans/langfuse-observability/phase-02/impl.
