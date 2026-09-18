# Oversized Session Fallback Implementation Plan

## Objective

Recover resumed Pi jobs when provider-managed session context exceeds capacity.
Preserve bounded task continuity. Avoid penalizing healthy targets for oversized
session state.

## Confirmed Design

`docs/plans/oversized-session-fallback/DESIGN.md`

## Prerequisite

Obtain one sanitized failing Pi JSON or stderr trace from the custom provider.
The trace must show the actual context-overflow response. Phase 1 must not invent
provider fields or depend on unverified message text.

## Scope

- Classify high-confidence Pi context-overflow failures.
- Expose whether tool activity occurred during an invocation.
- Recover on the same target using bounded stored turns.
- Retry the current prompt alone when reconstruction overflows.
- Prevent automatic replay after tool activity.
- Replace stale native sessions only after successful recovery.
- Preserve existing failover and target-health semantics otherwise.
- Add durable recovery events and regression coverage.

## Non-goals

- Pi RPC compaction.
- Model-generated summaries.
- Native session token estimation.
- Provider context-window configuration.
- New database schema fields.
- Public job resource changes.

**Commit:** `fix(execution): recover oversized backend sessions`

### Phase 1: Classify overflow and establish replay safety

**Task Guide Input:** Implement reliable Pi context-overflow classification and
an executor-visible tool-activity signal. Use a sanitized real failure trace from
the custom provider. Preserve existing backend outcomes and streaming behavior.
Do not implement session recovery during this phase.

**Goal:** Produce a stable `context_overflow` error code and trustworthy replay
eligibility evidence.

**Files:**
- Modify: `src/openmcp/backends/pi.py`
- Modify: `src/openmcp/drivers.py`
- Modify: `tests/test_smoke.py`
- Modify: `tests/test_execution.py`
- Modify when required by existing fixture conventions: `tests/test_streaming_backends.py`

**Tasks:**
1. Add the sanitized provider failure trace to test coverage.
2. Extract Pi assistant `stopReason` and `errorMessage` diagnostics.
3. Classify only high-confidence overflow signatures as `context_overflow`.
4. Ensure overflow classification overrides generic shell execution errors.
5. Track whether `tool.started` occurred within `StreamBridge`.
6. Preserve queue, cancellation, and event-draining behavior.

**Acceptance Criteria:**
- The captured provider trace returns `error_class="context_overflow"`.
- Structured assistant errors contribute diagnostic text.
- Recognized stderr overflow returns `context_overflow`.
- Similar generic errors remain normally classified.
- Authentication and invalid-model behavior remains unchanged.
- `DriverResult.error_code` preserves `context_overflow`.
- `StreamBridge` reports tool activity after `tool.started`.
- Assistant-only events never report tool activity.

**Reviewer Checklist:**
- Signature matching avoids broad false positives.
- Structured errors cannot be mistaken for successful output.
- Shell failure precedence preserves the specific error code.
- Error logs contain no prompts or native session identifiers.
- Activity tracking remains thread-safe.
- Existing streaming backpressure remains unchanged.

**Verification Checks:**
- `uv run pytest tests/test_smoke.py -k 'pi and (overflow or error or nonzero)'`
- `uv run pytest tests/test_execution.py -k 'stream_bridge'`
- `uv run pytest tests/test_streaming_backends.py -k 'pi'`

### Phase 2: Recover sessions before target failover

**Task Guide Input:** Implement same-target recovery for resumed sessions that
return `context_overflow`. First retry without the native session using existing
bounded stored turns. If reconstruction also overflows, retry the original prompt
alone. Skip duplicate prompt-only recovery. Block automatic replay after tool
activity. Replace stale sessions only after success. Keep normal failures,
failover, cancellation, and health accounting compatible.

**Goal:** Complete best-effort continuity recovery without misclassifying target
health.

**Files:**
- Modify: `src/openmcp/execution.py`
- Modify only if persistence behavior requires it: `src/openmcp/database.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_database.py`

**Tasks:**
1. Intercept resumed-session `context_overflow` before generic failure handling.
2. Retry the same target using `_with_history` and an empty session ID.
3. Retry the original prompt when reconstructed context also overflows.
4. Refuse automatic replay after observed tool activity.
5. Bypass target failure accounting for overflow recovery steps.
6. Persist successful replacement sessions with `clear_sessions=True`.
7. Store the original prompt and successful response exactly once.
8. Emit bounded recovery lifecycle events without sensitive data.

**Acceptance Criteria:**
- A resumed overflow retries the same target before another target.
- Reconstruction uses existing `history_turns` and `history_bytes` bounds.
- Prompt-only recovery runs only after reconstructed overflow.
- Prompt-only recovery is skipped when reconstruction adds nothing.
- Recovery does not consume another routing attempt.
- Overflow does not increment target consecutive failures.
- Genuine recovery failures use existing target-health handling.
- Tool activity blocks automatic replay.
- Successful recovery records target success.
- Successful recovery clears stale stream sessions atomically.
- Failed or cancelled recovery preserves prior session pointers.
- The completed turn is stored exactly once.
- The next standard job resumes the replacement session.
- Recovery events expose no prompt or session contents.
- Existing fresh-session behavior remains unchanged.

**Reviewer Checklist:**
- Recovery only starts for a nonempty resumed session.
- Recovery cannot loop indefinitely.
- The target semaphore covers every internal invocation.
- Stream recorders close correctly for every recovery path.
- Cancellation stops remaining recovery steps immediately.
- Circuit-breaker state ignores only context overflow.
- Session replacement occurs only after successful completion.
- Cross-target failover receives normal history behavior.
- Job attempt counts still represent target selections.

**Verification Checks:**
- `uv run pytest tests/test_execution.py -k 'overflow or recovery or fresh or history or retry'`
- `uv run pytest tests/test_database.py -k 'append_turn or session'`
- `uv run pytest tests/test_smoke.py -k 'pi'`
- `uv run pytest`
- `uv build`

## Overall Acceptance

- Oversized resumed Pi sessions recover on their selected target.
- Bounded exact history precedes prompt-only recovery.
- Normal failover begins only after recovery fails.
- Context overflow never degrades target health.
- Tool activity prevents automatic replay.
- Successful recovery replaces stale native sessions.
- Existing retry, fresh-session, streaming, and cancellation tests pass.
- The complete test suite and package build pass.

## Risks

- The custom provider may expose an unexpected error shape.
- Overflow could occur after partial tool execution.
- Internal reinvocation could complicate stream recorder lifecycle.
- Session replacement could duplicate stored turns if misplaced.

Each risk has explicit acceptance criteria and reviewer checks above.
