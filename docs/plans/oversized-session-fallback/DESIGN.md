# Oversized Session Fallback

## Purpose

Recover continued jobs when a provider-managed session exceeds the provider's
context window. Preserve task continuity where possible. Avoid treating one
oversized session as an unhealthy target.

The initial scope covers the Pi backend. The custom Pi provider supports a 384k
context window and does not compact oversized sessions automatically.

## Current Behavior

A standard job resumes a stored Pi session using `--session`. The provider
receives its complete native session state. OpenMCP cannot truncate that state.

Pi process failures currently become generic retryable failures. The executor
records a target failure and selects another configured target. Context overflow
therefore affects target health and may trigger unrelated provider failover.

OpenMCP stores completed prompts and responses separately from native session
pointers. When no native session exists, `_with_history` already reconstructs a
bounded prompt using `history_turns` and `history_bytes`.

## Decisions

- Add a stable `context_overflow` backend error code.
- Detect overflow using high-confidence Pi diagnostics.
- Recover on the selected target before cross-target failover.
- Start recovery without the oversized native session.
- First retry with bounded stored turn history.
- Then retry with the current prompt only.
- Skip duplicate prompt-only recovery when history adds nothing.
- Keep recovery inside one selected-target attempt.
- Do not count overflow as a target-health failure.
- Replace stored sessions only after recovery succeeds.
- Preserve the original submitted prompt in stored turns.
- Do not add generated summaries initially.
- Do not add provider context-window configuration initially.
- Do not add Pi RPC compaction initially.

## Recovery Flow

1. The executor selects a target normally.
2. The executor resumes the stored native session.
3. A non-overflow result follows existing handling.
4. A `context_overflow` result starts same-target recovery.
5. Recovery clears the session ID for the next invocation.
6. Recovery constructs bounded context from stored turns.
7. Successful reconstruction stores the replacement session.
8. Another overflow retries the current prompt alone.
9. Successful prompt-only recovery stores the replacement session.
10. Remaining failures enter normal cross-target failover.

Recovery does not consume another `max_attempts` slot. `max_attempts` continues
to represent selected-target routing attempts.

## Overflow Classification

`src/openmcp/backends/pi.py` will inspect structured Pi assistant failures.
Relevant fields include `stopReason="error"` and `errorMessage`.

The classifier will recognize a narrow signature set. Candidate signatures
include:

- `context_length_exceeded`
- `model_context_window_exceeded`
- `maximum context length`
- `context window` combined with `exceeded`
- `prompt too long` combined with a context limit

Generic phrases such as `too long` are insufficient. Classification must take
precedence over generic `execution_error` handling.

Implementation requires one captured failure from the custom provider. That
sample defines the canonical fixture and final signature set.

## Reconstructed Context

Recovery reuses the existing bounded-history format:

```text
Previous context:

User:
<previous prompt>

Assistant:
<previous response>

---

Current request:

<current prompt>
```

The existing daemon bounds remain authoritative:

```toml
[daemon]
history_turns = 8
history_bytes = 65536
```

Reconstruction preserves completed conversation turns. It does not preserve
Pi-only tool calls, tool results, or hidden provider state. Filesystem changes
remain available through the shared project directory.

No model-generated summary is required initially. Exact bounded turns avoid an
extra provider call, summary loss, and another failure path.

## Replay Safety

Automatic recovery is permitted only before meaningful tool activity.

If Pi reports overflow after tool activity or partial execution, the executor
must not replay automatically. It returns a specific failure instead. This
prevents duplicated filesystem changes or external side effects.

The captured provider trace must confirm whether overflow occurs before any
assistant or tool execution.

## Session Persistence

The oversized session remains stored until recovery succeeds. Cancellation,
provider failure, or persistence failure must retain existing session pointers.

After successful recovery, persistence will:

1. Clear sessions for the project, context key, and workflow.
2. Store the replacement target session when provided.
3. Store the original prompt and successful response once.

`Database.append_turn(clear_sessions=True)` already supports these transaction
semantics. Clearing other target sessions prevents later failover from resuming
stale native state.

The job-state update remains separate initially. Stronger job-state and context
atomicity may reuse or generalize `finish_fresh_job_success` later.

## Retry and Health Semantics

Context overflow describes session state, not target health.

The initial overflow and reconstruction overflow will not call
`_record_failure`. They will not increment consecutive failures or open the
target circuit.

A later timeout, transport failure, authentication failure, or provider failure
uses existing health accounting. A successful recovery records target success.

## Observability

Add durable events through the existing event mechanism:

- `target.context_overflow`
- `target.session_recovery_started`
- `target.session_recovery_finished`
- `target.session_replaced`

Events include the workflow, target identifier, recovery phase, outcome, and
error code. Events exclude prompts, responses, and native session identifiers.

The outer `target.attempt_finished` event reports the selected-target result.
Recovery events provide nested detail without creating routing attempts.

## Configuration and Migration

No database migration is required.

No `384000` token setting will be added. OpenMCP cannot accurately estimate the
provider-managed transcript, system context, and tool results.

No recovery-specific history limits will be added. Existing `history_turns` and
`history_bytes` remain sufficient until operational evidence shows otherwise.

A recovery policy setting is deferred. The initial behavior applies only to
high-confidence context overflow from resumed sessions.

## Rejected Alternatives

### Immediate cross-target failover

Rejected because the failure belongs to one session. It incorrectly penalizes
target health and may lose task continuity.

### Immediate fresh session

Rejected because stored turns provide useful bounded continuity at low cost.

### Model-generated summary

Deferred because it adds cost, latency, and another failure path. Exact bounded
turns provide deterministic initial behavior.

### Pi RPC compaction

Deferred because current Pi execution uses one-shot JSON mode. RPC compaction
requires bidirectional framing, process lifecycle management, cancellation,
timeouts, and command correlation.

Native compaction remains a later enhancement when preserving Pi-specific state
justifies that complexity.

## Testing

Backend tests will cover:

- Structured Pi overflow extraction.
- Stderr overflow extraction.
- Generic similar messages that are not overflow.
- Overflow precedence over generic execution errors.
- Captured custom-provider overflow output.

Execution tests will cover:

- Same-target reconstruction before failover.
- Successful replacement without secondary target use.
- Reconstruction overflow followed by prompt-only recovery.
- Skipping duplicate prompt-only recovery.
- Genuine recovery failure followed by normal failover.
- No health penalty from context overflow.
- Target success after successful recovery.
- Cancellation during recovery.
- No automatic replay after tool activity.
- Replacement session resumed by the next job.
- Original prompt stored exactly once.

Database tests will cover:

- Session replacement after successful recovery.
- Existing sessions retained after failed recovery.
- Transaction rollback preserving prior sessions.

## Acceptance Criteria

- A resumed oversized Pi session triggers same-target recovery.
- Bounded reconstruction runs before prompt-only recovery.
- Cross-target failover runs only after recovery fails.
- Context overflow does not affect target health.
- Successful recovery replaces obsolete session pointers.
- The successful turn is stored exactly once.
- Recovery never replays observed tool activity.
- Existing non-overflow retry behavior remains unchanged.

## Non-goals

- Predicting native session token usage.
- Preserving the complete Pi native transcript.
- Adding provider-specific context-window configuration.
- Adding model-generated context summaries.
- Implementing Pi RPC compaction.
- Changing the public job resource shape.
