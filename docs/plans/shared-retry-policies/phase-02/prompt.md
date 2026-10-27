## User Request
Continue shared-retry-policies on main. Execute Phase 2 only. The user approved conservative replay guards, separate context recovery accounting, fresh manual retry budgets, and a narrow telemetry rollover correction. Leave the worker-job-telemetry plan untouched.

## Phase
2: Bounded silent retries with replay protection

## Tasks
- task-1: Add policy matching and bounded same-target policy attempts using the immutable Phase 1 snapshot. Keep context-overflow recovery separate and check cancellation before every additional invocation.
- task-2: Preserve sequential attempt observability, streams, ask tokens, sessions, capacity and probe ownership; finalize health once and store one successful turn. Correct only retry-required telemetry rollover.
- task-3: Add deterministic regression tests for every acceptance criterion and lifecycle exit, using fake drivers and boundary mocks.

## Context
Read docs/plans/shared-retry-policies/PLAN.md and DESIGN.md. Phase 1 is independently reviewed at refs/plans/shared-retry-policies/phase-01/impl. ExecutionPlan.retry_policy(target_id) returns immutable resolved RetryPolicy values: retry_attempt, error_codes, error_patterns. No live configuration lookup.
Consultation 556ea624-0f44-4357-a0af-c75eb8e1b03e identified these integration constraints:
- Do not loop around execute() because it selects targets and claims probes. Do not call unchanged _execute_attempt() repeatedly because it releases capacity and _complete_attempt() updates health/stores turns.
- Select once; hold selected target capacity and half-open probe throughout the immediate sequence. Each policy attempt owns its recorder and ask token. Selected-target execution owns accumulator and final-only health/store.
- Protect cleanup beginning immediately after target selection, including _prepare_session, target.selected persistence, ask issuance/revocation, recorder and finalization failures. One cleanup failure must not skip other cleanup. Preserve existing exception outcomes; do not reclassify arbitrary exceptions.
- No StreamBridge means unobserved tool activity, not safe replay. Unknown replay safety blocks policy retries. Tool observation must remain independent of transcript quotas/persistence. Do not change drivers.py in this phase.
- Preserve recovery phase, effective prompt/session, replacement/reconstruction flags and replay evidence when a recovery invocation fails transiently. Retry that eligible invocation without restarting stale-session overflow/reconstruction. Preserve session replacement bookkeeping through final success.
- Policy attempts are bounded by retry_attempt + 1. Overflow recovery can add internal invocations but must retain its existing bounded progress independently. Fresh budget per explicit manual retry; durable attempt numbering remains cumulative.
- Use one TelemetryAccumulator across attempts. Rollover each actual attempt exactly once, finalize each invocation separately, retain deduplication by attempt/invocation. Never call Database.reset_retry for automatic retry.
- telemetry.py has a rollover risk: load 100 completed input tokens, add 150 in another attempt, complete it; completed aggregate becomes 250 but completed measurement may still say 150, causing snapshot underreporting when next attempt has no usage. Reproduce test-first, then correct narrowly.
Baseline ef9f219 passed all plan checks. Phase 1 product tree passed 787 server tests, 15 live deselections. Existing environment/style warnings are not reasons to refactor adjacent code.

## Files
Modify only:
- server/src/refract/execution.py
- server/src/refract/telemetry.py
- server/tests/test_execution.py
- server/tests/test_telemetry.py
- server/tests/test_target_capacity.py
- server/tests/test_runtime.py
Coordination output only:
- docs/plans/shared-retry-policies/phase-02/notes.md
- docs/plans/shared-retry-policies/phase-02/journal.md

## Done When
- retryAttempt = 9 permits at most ten policy attempts; success stops immediately. Zero/absent policies and unmatched rules invoke target once.
- Codes match exactly OR error patterns match case-insensitive substrings. Both lists empty allow all otherwise eligible transient outcomes.
- Only normalized RETRYABLE driver outcomes can retry. Rules cannot promote fatal, cancelled, context-overflow or replay-blocked results. Arbitrary exceptions are not converted.
- Tool activity or unknown replay safety blocks replay; final-only execution requires trustworthy safety evidence.
- Each explicit manual retry gets a fresh policy budget with cumulative durable attempt numbers.
- Cancellation before additional invocations and during waits stops remaining attempts; all resources release.
- Intermediate attempt failures do not terminate jobs, notify terminal state, open breakers or switch targets.
- Exhaustion preserves existing final failure and coordinator next_target/fallback metadata. Manual fallback semantics remain unchanged.
- Context-overflow recovery remains independently bounded and does not restart completed recovery stages after transient failure.
- Half-open probes cannot overlap; target permits/probes/ask tokens/recorders clean up on normal, cancellation, setup, exception and finalization exits.
- Every actual attempt has distinct sequential records/events/stream boundaries. Successful conversation turn is stored once, retaining recovery session replacement.
- Telemetry includes all attempts and recovery invocations without duplicates, including manual-to-automatic rollover with missing next usage, cache totals and context invalidation.
- Existing no-policy execution tests remain passing; add focused fake-driver tests for budget/exhaustion, OR matching, exclusions, tool activity after truncation, unknown observation, recovery-to-transient-to-success, cancellation, final-only health, concurrent probe ownership and injected cleanup failures.
- `cd server && uv run --extra dev pytest tests/test_execution.py tests/test_telemetry.py tests/test_target_capacity.py tests/test_runtime.py`
- `git diff --check`

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Test-first for behavior changes; characterize before refactoring. Quote actual RED failures and GREEN results for each task. Avoid speculative abstractions and unrelated formatting changes. No new dependencies, backoff configuration, automatic switching, database migrations, live probes, daemon restarts or Git operations. Do not edit earlier phases, plan/design/handover, dashboard, drivers or telemetry plan. Ask via refract ask if unresolved scope/design prevents completion.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line. Declare all touched paths, including notes and journal.
