## Original User Request

Recover continued Pi jobs whose native sessions exceed provider context capacity.
Preserve best-effort continuity before cross-target failover.

## Phase

Recover oversized sessions before target failover.

## Preconditions

Phase 1 must be complete and verified:

- the sanitized provider trace is covered;
- Pi returns `DriverResult.error_code == "context_overflow"`;
- `StreamBridge` exposes per-invocation `tool.started` evidence;
- Phase 1 streaming and cancellation checks pass.

Do not parse provider diagnostics in this phase.

## Objective

Recover a resumed oversized session on its selected target. First retry with
bounded stored history. Then retry the original prompt alone when needed.
Preserve replay safety, health semantics, streaming, persistence, and routing
attempt accounting.

## Files

Modify only when required:

- `src/openmcp/execution.py`
- `src/openmcp/database.py`
- `tests/test_execution.py`
- `tests/test_database.py`
- `docs/plans/oversized-session-fallback/phase-02/notes.md`
- `docs/plans/oversized-session-fallback/phase-02/journal.md`

Relevant symbols:

- `TargetExecutor.execute`
- `TargetExecutor._with_history`
- `TargetExecutor._record_failure`
- `StreamBridge`
- `StreamRecorder`
- `Database.append_turn`
- `Database.session`
- `Database.recent_turns`
- `Database.event`

## Fixed Recovery Order

```text
resumed native session
-> context_overflow
-> same target, empty session, bounded stored history
-> context_overflow
-> same target, empty session, original prompt only
-> remaining failure
-> normal cross-target routing
```

Recovery stays inside one selected-target routing attempt.

## Tasks

### Task 1: Add deterministic recovery tests

Create the smallest local driver double recording:

- target ID;
- session ID;
- prompt;
- emitted tool activity;
- scripted `DriverResult` values.

Add failing tests for:

1. Resumed overflow followed by successful reconstruction.
2. Reconstruction overflow followed by prompt-only success.
3. Duplicate prompt-only suppression when history adds nothing.
4. Tool activity during the resumed call.
5. Tool activity during reconstruction.
6. Ordinary recovery failure followed by normal failover.
7. All bounded calls overflowing before normal failover.
8. Cancellation during recovery.
9. Successful replacement resumed by the next job.
10. Original prompt and completed turn stored exactly once.

Assert exact invocation order and arguments.

### Task 2: Refactor one target attempt for internal invocations

Refactor only enough to support bounded internal calls:

```text
select target
-> acquire target semaphore once
-> record job attempt once
-> create one StreamRecorder
-> run invocation with a fresh StreamBridge
-> drain and close that bridge
-> optionally run another invocation with another bridge
-> record one outer attempt.finished
-> close recorder
-> release semaphore once
```

Requirements:

- one bridge per invocation;
- one activity flag per invocation;
- one recorder per selected target;
- one target semaphore across the full recovery sequence;
- one `record_job_attempt` call per selected target;
- one recorder-level `attempt.finished` event;
- accepted stream events drain before proceeding.

Prefer one small helper that runs and drains one invocation.

### Task 3: Intercept eligible overflow only

Recovery starts only when:

```text
original session ID is nonempty
and result.error_code == context_overflow
and no tool.started was observed
```

Do not start this recovery for:

- explicit `fresh_session=True` jobs;
- already-sessionless standard jobs;
- ordinary backend failures;
- cancellation;
- request-fatal results.

A sessionless standard job keeps existing `_with_history()` behavior.

### Task 4: Run bounded same-target recovery

First recovery call:

```text
session_id = ""
prompt = self._with_history(project.id, context_key, workflow, original_prompt)
```

Reuse existing `history_turns` and `history_bytes` exactly.

If that call also returns `context_overflow` without tool activity, run one
prompt-only call only when:

```text
reconstructed_prompt != original_prompt
```

The prompt-only call uses:

```text
session_id = ""
prompt = original_prompt
```

Maximum same-target invocations:

- three when reconstruction adds history;
- two when reconstruction equals the original prompt.

Do not create a loop.

### Task 5: Enforce replay safety and health semantics

Before every automatic replay, inspect that invocation's tool-activity signal.

```text
context_overflow plus tool activity
-> stop all automatic replay
-> no same-target recovery
-> no cross-target failover
-> return existing context_overflow result
```

Any `tool.started` blocks replay. Tool completion does not matter.

Do not call `_record_failure()` for any `context_overflow` recovery step.

Apply existing failure accounting when a recovery call returns a genuine
non-overflow target failure. Preserve current cancellation and request-fatal
handling. Successful recovery records target success.

### Task 6: Replace sessions only after success

On recovered standard success, call existing persistence with:

```text
clear_sessions=True
prompt=original_prompt
response=successful_result.text
session_id=successful_result.session_id
```

Requirements:

- never clear sessions before success;
- clear sessions only for the same project, context key, and workflow;
- store a replacement only when its session ID is nonempty;
- store the original submitted prompt;
- append one completed turn;
- preserve unrelated streams;
- preserve old sessions on cancellation or persistence rollback.

Reuse `Database.append_turn(clear_sessions=True)`. Add no database API unless a
verified gap requires it.

Ordinary non-recovery success retains `clear_sessions=False`. Explicit fresh
jobs retain `finish_fresh_job_success()` behavior.

### Task 7: Emit bounded recovery events

Use `Database.event()` for:

- `target.context_overflow`
- `target.session_recovery_started`
- `target.session_recovery_finished`
- `target.session_replaced`

Payloads may contain only low-cardinality fields:

- workflow;
- target;
- recovery phase, `reconstruct` or `fresh`;
- outcome;
- error code.

Exclude prompts, responses, history, session IDs, and raw diagnostics.

Emit `target.session_replaced` only after successful persistence.
Do not replace the outer `target.attempt_finished` event.

### Task 8: Verify database, routing, and regressions

Extend database tests only as needed to prove:

- multiple stale sessions in one stream are cleared;
- one replacement remains;
- unrelated streams remain;
- rollback preserves prior sessions.

Verify routing semantics:

- internal recovery does not consume `max_attempts`;
- `job.attempts` counts selected targets;
- overflow does not alter circuit state;
- ordinary recovery failure uses current health handling;
- final overflow without tool activity may proceed to another target;
- tool activity blocks cross-target replay.

## Expected Control Flow

### Reconstruction succeeds

```text
select primary
-> resume old session
-> context_overflow, no tool activity
-> reconstruct with empty session
-> SUCCESS
-> record target success
-> append_turn(clear_sessions=True)
-> emit session_replaced
```

### Prompt-only succeeds

```text
resume -> overflow
reconstruct -> overflow
prompt-only -> SUCCESS
-> atomically replace sessions and store original turn
```

### No history exists

```text
resume -> overflow
_with_history returns original prompt
-> one empty-session original-prompt call
-> never repeat the identical call
```

### Ordinary recovery failure

```text
resume -> overflow, health unchanged
reconstruct -> ordinary target failure, normal health accounting
-> secondary target may be selected
```

### All bounded calls overflow

```text
resume -> overflow
reconstruct -> overflow
prompt-only -> overflow
-> health unchanged
-> secondary target may be selected
```

### Overflow after tool activity

```text
invocation emits tool.started
-> context_overflow
-> no automatic replay anywhere
-> preserve sessions
-> return context_overflow
```

### Cancellation

```text
recovery invocation cancelled
-> drain accepted events
-> stop recovery and failover
-> preserve sessions
```

## Edge Cases

Cover:

- old session with no stored turns;
- history bounds excluding every turn;
- replacement success with empty session ID;
- multiple stale target sessions;
- unrelated context and workflow sessions;
- reconstructed and prompt-only overflow;
- ordinary timeout or backend error during recovery;
- target-fatal and request-fatal recovery results;
- cancellation before and during recovery;
- assistant text without tool activity;
- secondary target available after unsafe replay evidence;
- `max_attempts == 1`;
- persistence failure after provider success.

## Invariants

- Recovery begins only for a resumed nonempty session.
- Same-target recovery precedes cross-target routing.
- Reconstruction precedes prompt-only fallback.
- Recovery is bounded.
- Duplicate prompt-only calls are skipped.
- Every recovery call uses an empty session ID.
- Existing history bounds remain authoritative.
- Tool activity blocks every automatic replay.
- Overflow never increments target failures.
- Ordinary failures retain existing health semantics.
- One selected target equals one recorded job attempt.
- The target semaphore covers internal recovery.
- Each bridge closes and drains correctly.
- Sessions remain until successful replacement.
- Replacement and turn insertion remain atomic.
- The stored turn uses the original prompt exactly once.
- Existing fresh and non-overflow behavior remains unchanged.

## Done When

- Resumed overflow retries the same target first.
- Recovery uses existing bounded history.
- Prompt-only fallback runs only when required.
- Duplicate calls are suppressed.
- Internal recovery does not consume routing attempts.
- Overflow remains health-neutral.
- Genuine failures retain current accounting.
- Tool activity blocks all replay.
- Cancellation stops remaining work.
- Successful recovery records target success.
- Successful recovery atomically replaces sessions.
- Failed recovery preserves sessions.
- The completed turn is stored exactly once.
- The next job resumes the replacement session.
- Recovery events expose no sensitive content.
- These commands pass:

```text
uv run pytest tests/test_execution.py -k 'overflow or recovery or fresh or history or retry'
uv run pytest tests/test_database.py -k 'append_turn or session'
uv run pytest tests/test_smoke.py -k 'pi'
uv run pytest
uv build
```

## Non-goals

- Pi RPC compaction.
- Generated summaries.
- Token estimation or overflow prediction.
- Provider window configuration.
- Recovery-specific history limits.
- Database schema changes.
- Public job-resource changes.
- New driver outcomes.
- Unbounded retries.
- Separate recovery target selection.
- Session deletion before success.
- Recovery for explicit fresh jobs.
- A separate replay-unsafe error code.

## Rules

Follow the supplied worker contract. Use test-driven development. Stay within
scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
