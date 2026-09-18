## Original User Request

Recover continued Pi jobs whose native sessions exceed provider context capacity.
Preserve best-effort continuity before cross-target failover.

## Phase

Classify overflow and establish replay safety.

## Prerequisite

Do not implement this phase without one sanitized real Pi context-overflow trace.
The trace must contain the actual failing JSON stream or stderr. It must exclude
prompts, credentials, tokens, and native session identifiers.

Use the trace to confirm:

- the diagnostic channel and event shape;
- whether `message.stopReason == "error"` appears;
- whether `message.errorMessage` appears;
- whether Pi exits nonzero;
- whether partial assistant output appears;
- whether any tool activity precedes overflow;
- the narrow signature defining `context_overflow`.

Do not invent provider fields or finalize candidate signatures without this
trace.

## Captured Trace Evidence

Job `b84cd27a-4afb-419f-b720-42b352854ddc` supplied the prerequisite evidence.
Its first resumed Pi invocation appended one user message followed by this
sanitized assistant message record:

```json
{
  "type": "message",
  "message": {
    "role": "assistant",
    "content": [],
    "stopReason": "error",
    "errorMessage": "502: {\"message\":\"No ChatGPT effort available to this account can carry a Bigger Context stage with <estimated_tokens> estimated tokens and <characters> characters.\",\"type\":\"invalid_request_error\",\"param\":null,\"code\":\"context_length_exceeded\"}"
  }
}
```

Confirmed properties:

- the stable provider code is `context_length_exceeded`;
- the diagnostic is inside assistant `errorMessage`;
- `stopReason` is `error`;
- assistant content is empty;
- Pi exited with status zero;
- no tool activity occurred during this invocation;
- existing OpenMCP classified the result as `no_agent_messages`.

Use the existing Pi JSON-mode `message_end` fixture shape around this sanitized
assistant payload. Classify the exact `context_length_exceeded` code. Do not
classify the account-specific prose or numeric estimates.

## Objective

Produce a stable `context_overflow` backend error code. Expose a thread-safe,
per-invocation signal indicating whether `tool.started` occurred.

Do not implement recovery in this phase.

## Files

Modify only when required:

- `src/openmcp/backends/pi.py`
- `src/openmcp/drivers.py`
- `tests/test_smoke.py`
- `tests/test_execution.py`
- `tests/test_streaming_backends.py`
- `docs/plans/oversized-session-fallback/phase-01/notes.md`
- `docs/plans/oversized-session-fallback/phase-01/journal.md`

Relevant symbols:

- `pi._message_text`
- `pi._extract_output`
- `pi._execute_sync`
- `StreamBridge`
- `DriverResult`
- driver normalization

## Tasks

### Task 1: Capture the real overflow regression

1. Add the sanitized provider trace as a test fixture.
2. First prove the fixture lacks `context_overflow` classification.
3. Preserve the trace's actual event and stderr shape.
4. Record unresolved trace-dependent details in `notes.md`.

### Task 2: Extract structured assistant failures

1. Add tests for assistant `message_end` events with:
   - `stopReason == "error"`;
   - string `errorMessage`;
   - empty or partial assistant content.
2. Extend Pi extraction narrowly.
3. Retain existing session, assistant text, top-level `error`, and
   `server_error` extraction.
4. Ensure partial assistant text cannot convert a structured failure into
   success.
5. Ignore arbitrary unknown fields.

### Task 3: Classify context overflow conservatively

1. Derive the matcher from the sanitized trace.
2. Match exact tokens or constrained phrase combinations.
3. Match diagnostic material only, not normal assistant prose.
4. Add close negative cases such as generic `too long` or `context error`.
5. Avoid token estimation and context-window configuration.

Candidate strings in `DESIGN.md` are evaluation guidance only. They are not an
approved signature set.

### Task 4: Preserve error precedence

Implement this effective precedence:

1. Cancellation remains `cancelled`.
2. Confirmed context overflow becomes `context_overflow`.
3. Existing fatal authentication and model handling remains unchanged.
4. Other structured assistant failures remain failures.
5. Ordinary process failures remain `execution_error`.

Confirmed overflow must override generic `execution_error`, including nonzero
Pi exits with partial assistant output.

Do not change `BackendResult` or add a driver outcome.

### Task 5: Preserve the driver error code

Add a regression proving:

```text
BackendResult.error_class = context_overflow
DriverResult.outcome = RETRYABLE
DriverResult.error_code = context_overflow
```

Do not add recovery to driver execution.

### Task 6: Track replay-safety evidence

1. Add `StreamBridge` tests before production changes.
2. A new bridge reports no tool activity.
3. Assistant deltas do not mark activity.
4. `tool.completed` alone does not mark activity.
5. `tool.started` permanently marks activity.
6. Closing and draining preserve the signal.
7. Implement the signal with a thread-safe primitive such as
   `threading.Event`.
8. Keep event enqueueing, capacity, backpressure, sentinel, cancellation, and
   drain behavior unchanged.

The signal answers only whether that invocation observed `tool.started`.

## Expected Control Flow

### Successful Pi invocation

```text
Pi events
-> extract session and assistant output
-> no structured failure
-> existing backend classification
-> SUCCESS
```

### Structured assistant failure

```text
assistant stopReason=error
-> extract errorMessage
-> preserve failure even with partial text
-> existing non-overflow normalization
```

### Context overflow

```text
confirmed JSON or stderr diagnostic
-> Pi-specific matcher
-> BackendResult.error_class=context_overflow
-> DriverResult.outcome=RETRYABLE
-> DriverResult.error_code=context_overflow
```

### Tool activity

```text
provider thread emits tool.started
-> activity flag set
-> event enqueued unchanged
-> executor can inspect the flag after invocation
```

## Edge Cases

Cover:

- nonzero exit with partial assistant output and overflow;
- structured failure with empty output;
- structured failure with partial output;
- normal assistant completion;
- stderr overflow when present in the real trace;
- authentication and invalid-model failures;
- close false-positive diagnostics;
- cancellation during failure handling;
- assistant-only streaming;
- repeated `tool.started` events;
- activity evidence after close and drain.

## Invariants

- Detection remains Pi-specific and high-confidence.
- The sanitized trace defines the canonical matcher.
- Cancellation takes precedence.
- Authentication and invalid-model behavior remains unchanged.
- `DriverResult.error_code` preserves `context_overflow`.
- No new `DriverOutcome` exists.
- No recovery exists in Phase 1.
- `StreamBridge` queue behavior remains unchanged.
- Activity tracking performs no persistence.
- Logs contain no prompts or native session identifiers.

## Done When

- The sanitized real trace is covered by tests.
- That trace produces `error_class="context_overflow"`.
- Structured assistant errors contribute diagnostics.
- Partial text cannot hide structured failure.
- Similar generic errors remain non-overflow.
- Existing fatal classifications remain unchanged.
- Driver normalization preserves `context_overflow`.
- `StreamBridge` reports only observed `tool.started` activity.
- Existing streaming and cancellation regressions pass.
- These commands pass:

```text
uv run pytest tests/test_smoke.py -k 'pi and (overflow or error or nonzero)'
uv run pytest tests/test_execution.py -k 'stream_bridge'
uv run pytest tests/test_streaming_backends.py -k 'pi'
```

## Non-goals

- Same-target recovery.
- Reconstructed-history retry.
- Prompt-only retry.
- Failover changes.
- Session replacement.
- Target-health changes.
- Recovery events.
- Database changes.
- Generated summaries.
- Pi RPC compaction.
- Token estimation.
- Provider window configuration.

## Rules

Follow the supplied worker contract. Use test-driven development. Stay within
scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
