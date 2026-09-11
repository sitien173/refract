<!-- ccg-shared-version: 10.5.0 -->

# Phase 2 — Journal: Provider normalization and execution bridge

## META

- Plan: docs/plans/worker-dashboard-streaming/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: ed7e1e88-28dd-42cb-9427-165f30d7c14c; repairs 8311d5e7-44d7-4f66-93e8-1aff2ad49c60, 13c220ec-e374-408f-a10c-9b100e16f36c, daa75c3a-02ac-4977-8a85-7e648221e603
- Review Job: pending
- Started: 2026-09-11T05:41:20Z
- Finished: pending

## Implementation Response

### Phase Goal
Normalize safe provider events and bridge worker-thread output into the durable stream recorder.

### Actions Taken
- Task 1 (RED): Added characterization fixtures and tests in `tests/test_streaming_backends.py` for Claude, Codex, Pi, and Agy. Verified exclusion of secrets, reasoning, and tool arguments/results.
- Task 2 (GREEN): Added optional `emitter` parameter to `ClaudeParams`, `CodexParams`, `PiParams`, and `AgyParams`. Configured Claude to use `stream-json` and `--include-partial-messages`, Agy to use `stream-json`, Codex to normalize items from `exec --json`, and Pi to normalize JSON mode events. Preserved authoritative final result extraction and session extraction unchanged.
- Task 3 (RED/GREEN): Added `StreamBridge` in `src/openmcp/drivers.py` with 256-slot bounded queue, blocking backpressure from provider worker threads, sentinel closure, and event-loop close handling. Tested backpressure, sentinel drain, and confirmed zero SQLite access on provider threads.
- Task 4 (RED/GREEN): Integrated `StreamBridge` and `StreamRecorder` in `TargetExecutor.execute()`. Ensured accepted events flush before target lifecycle finish and terminal job state. Added pre-execution capability detection `supports_structured_streaming` on `DriverRegistry` cached per resolved executable path with clean final-only fallback when streaming is unsupported or emitter is None (omits structured flags and avoids prompt retry). Resolved deadlock in test fake drivers by running synchronous emitters inside worker threads via `asyncio.to_thread`. Fixed blocking defect where `src/openmcp/drivers.py` omitted `import subprocess`, restoring functional `--help` capability probe execution.
- Task 5 (RED/GREEN): Resolved review findings: isolated Agy terminal assistant content rejecting object payloads and diagnostic lines, preventing tool argument/result/secret leakage into agent messages and job text; normalized Pi real `message_update.assistantMessageEvent.type == "text_delta"` and camelCase `toolCallId`/`toolName` event shapes with `isError` mapping; unwrapped Claude `stream_event` envelopes for partial messages and terminal result extraction; switched Codex capability check to probe `codex exec --help`; coordinated synthetic assistant entity IDs across Agy continuations.

### Verification Evidence
- `uv run pytest tests/test_streaming_backends.py tests/test_execution.py tests/test_live_backends.py -m 'not live'`: 50 passed, 3 deselected in 10.91s.
- `git diff --check`: Clean, zero whitespace issues.

# EXTERNAL RESPONSE
## META
- Phase: 2
- Started: 2026-09-11T05:41:20Z
- Finished: 2026-09-11T07:52:45Z
- Plan dir: docs/plans/worker-dashboard-streaming/phase-02
## SUMMARY
Normalized safe provider events and bridged worker-thread output to durable stream recording.
## FILES MODIFIED
| Action | Path | Change |
| --- | --- | --- |
| Modified | src/openmcp/backends/agy.py | Isolated terminal assistant text and coordinated continuation entity IDs. |
| Modified | src/openmcp/backends/claude.py | Unwrapped stream_event envelopes for partial messages and results. |
| Modified | src/openmcp/backends/codex.py | Normalized safe JSONL assistant and tool lifecycle events. |
| Modified | src/openmcp/backends/pi.py | Normalized real message_update and tool_execution event shapes. |
| Modified | src/openmcp/drivers.py | Added bounded bridge and probed codex exec --help for capability check. |
| Modified | src/openmcp/execution.py | Drained and flushed stream data before lifecycle completion. |
| Modified | tests/test_execution.py | Added bridge, ordering, attempt, and capability coverage. |
| Created | tests/test_streaming_backends.py | Added sanitized backend characterization fixtures. |
| Modified | docs/plans/worker-dashboard-streaming/phase-02/notes.md | Recorded task decisions and test evidence. |
| Modified | docs/plans/worker-dashboard-streaming/phase-02/journal.md | Recorded implementation evidence. |
## NOTES
- docs/plans/worker-dashboard-streaming/phase-02/notes.md, Tasks 1 through 5
## SPEC COMPLIANCE
- Meets Spec? YES - Required non-live Phase 2 verification passed.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

Phase 2 completed. Journal: docs/plans/worker-dashboard-streaming/phase-02/journal.md.

## Quality Review

<!-- Coordinator appends the independent review response here. -->

## Review Result

- Spec Status: PENDING
- Debt: none

## Final Commit

- Implementation: pending
- State record: this journal update's commit
