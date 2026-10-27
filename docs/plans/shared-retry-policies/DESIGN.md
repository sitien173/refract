# Shared Retry Policies Design

**Status:** Confirmed 2026-10-27
**Consultation:** Completed through Refract job `556ea624-0f44-4357-a0af-c75eb8e1b03e`. The user approved its clarifications and narrow Phase 2 telemetry correction. The user authorized execution on `main` without waiting for telemetry plan completion.

## Purpose

Retry transient target failures silently within the submitted job. Define reusable rules once, then reference them from multiple targets.

## Users and Success Criteria

Operators configure named retry policies in global TOML. Targets share policies by name.

- `retryAttempt` counts retries after the initial attempt.
- `retryAttempt = 9` permits ten policy attempts. Context-overflow recovery may add internal driver invocations.
- Each explicit manual retry receives a fresh policy budget. Durable attempt numbering remains cumulative.
- Error codes and message patterns use OR matching.
- Intermediate failures do not terminate the job.
- Attempts remain observable through existing logs and transcripts.
- No policy reference preserves existing execution behavior.

## Constraints and Non-Goals

- Preserve the separate `worker-job-telemetry` plan and changes.
- Do not implement, commit, stash, or reset during planning.
- No target-level overrides or inline retry policies.
- No project-local policy definitions or policy inheritance.
- No automatic target switching or changed fallback semantics.
- No new dependencies, regex engine, or retry backoff configuration.
- Policy definitions are edited in TOML, not a new dashboard policy editor.
- Preserve existing context-overflow recovery and manual retry behavior.

## Chosen Approach

Define named policies under `retryPolicies`. Each target optionally references one policy through `retryPolicy`.

```toml
[retryPolicies.transient]
retryAttempt = 2
errorCodes = ["rate_limit"]
errorPatterns = ["temporarily unavailable"]

[[targets]]
id = "primary"
backend = "pi"
retryPolicy = "transient"

[[targets]]
id = "secondary"
backend = "codex"
retryPolicy = "transient"
```

The example illustrates configuration shape, not guaranteed backend error codes.

Rejected: target-local rules duplicate shared configuration.
Rejected: shared policies plus local overrides complicate resolution.

### Policy Contract

- `retryAttempt`: nonnegative integer, default `0`. Reject booleans.
- `errorCodes`: list of nonempty strings, default `[]`.
- `errorPatterns`: list of nonempty strings, default `[]`.
- Match codes exactly against `DriverResult.error_code`.
- Match patterns as case-insensitive substrings of `DriverResult.error`.
- Either list may match; both lists empty allow all eligible transient failures.
- Configured rules restrict eligible failures; they cannot override safety exclusions.
- Reject unknown policy fields, malformed declarations, and unknown references.
- An absent reference, or a cleared dashboard reference, disables retries.
- Reject target-local `retry` and `retryAttempt` declarations rather than silently ignoring them.

## Architecture and Data Flow

1. Global configuration parses and validates shared policies.
2. Target references resolve against the validated global registry.
3. Submission snapshots resolved retry settings into the immutable execution plan.
4. Execution reads the snapshot, not current configuration.
5. A transient result passes safety checks and rule matching.
6. Remaining budget permits another attempt on the same target.
7. Success, exclusion, cancellation, or exhausted budget ends execution.
8. Existing job finalization and fallback metadata handle the final result.

Legacy persisted plans without retry settings execute without retries. Changes to policy definitions affect newly submitted jobs only.

Retry metadata must not change backend session identity. Preserve existing target execution keys when only retry settings change. Keep retry settings in durable execution-plan serialization, separate from the identity payload.

The dashboard exposes and preserves target policy references through existing target read and mutation paths. Use a simple named-reference input; server validation rejects unknown names. Shared policy definitions remain TOML-managed.

## Errors and Edge Cases

Only normalized `RETRYABLE` outcomes are eligible. Never automatically retry cancellation, `REQUEST_FATAL`, `TARGET_FATAL`, context overflow, or replay-blocked failures. Existing session recovery remains separate from the retry budget.

Observed tool activity blocks replay even when rules match. Preserve conservative handling when replay safety cannot be established. Test both streaming and non-streaming paths. Unknown replay safety blocks automatic retries; final-only execution requires trustworthy replay-safety evidence.

Retries remain inside one job and retain sequential attempt numbers. Do not emit terminal job notifications between attempts. Keep attempt events, transcripts, and cumulative token usage. Store a successful conversation turn once.

Check cancellation before each retry and during existing waits. Release concurrency capacity, stream recorders, ask tokens, and circuit probe ownership on every exit. Intermediate failures must not open the breaker before permitted retries finish. Update final target health consistently with the final execution result.

Use bounded immediate retries without introducing delays. Preserve current invocation timeout semantics; do not silently reinterpret workflow timeouts. Do not retry arbitrary Python exceptions as transient driver results.

## Migration

Existing TOML needs no changes. New policy sections are optional. Legacy execution plans default to disabled retries. No database schema migration is intended.

Configuration diagnostics must not echo sensitive message patterns. Target mutations must preserve unrelated policies, comments, and revision-conflict safeguards.

## Testing

Use deterministic fake drivers. Cover configuration validation, shared references, immutable snapshots, legacy plan parsing, identity stability, exact retry budgets, OR matching, exclusions, cancellation, replay safety, capacity cleanup, breaker handling, session recovery, cumulative telemetry, and dashboard round trips.

Run baseline tests after the telemetry plan finishes. Tests and builds were not run during this planning session. No live backend probes are authorized by this plan.

## Risks and Open Questions

- Automatic replay can duplicate tool actions. Existing replay guards remain mandatory.
- Additional attempts consume tokens and execution time.
- The user waived waiting for telemetry completion. Preserve its plan and existing commits.
- Consultation identified a telemetry rollover risk after manual and automatic retries. Phase 2 may narrowly correct `server/src/refract/telemetry.py`, with regression coverage.
- Baseline verification remains pending. Anchor a clean verified plan base before Phase 1.
