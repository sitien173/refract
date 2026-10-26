<!-- refract-shared-version: 2.0.0 -->

# Phase 2 — Journal: Correct usage collection across existing backend streams

## META

- Plan: docs/plans/worker-job-telemetry/PLAN.md
- Implementation Profile: implement
- Consultation Profile: n/a
- Review Profile: base
- Implementation Jobs: b63723ee-d416-4123-ac7a-c76e35de41e4; 131dcfed-3364-46c1-85d1-bf7c03e3c420; b8db30c2-286b-4459-b5e1-8a71dae6a439
- Review Jobs: 8012f51b-f94d-4cd5-bcaa-75b96e1c5fe8; 5df2c213-05d5-41ea-9fdf-59165cababe8
- Started: 2026-10-26T18:51+07:00
- Finished: pending

## Implementation Response

- Recovered terminal fix cycle 1 with six declared paths. Inspected diff.
- Fresh coordinator verification at 273e2ce: 685 passed, 11 deselected.
- Fix cycle 2 returned TASK_COMPLETE. Seven declared paths match diff.
- Worker recorded regression RED and GREEN evidence in notes.md.
- Fresh coordinator verification of cycle 2: `cd server && uv run pytest` passed, 692 passed, 11 deselected, 122.24 seconds.

## Quality Review

- Initial review: FAIL. Pi identity, unknown input, Codex malformed usage, context provenance.
- Cycle 1 re-review: FAIL. Turn lifecycle, invalid cache components, Pi context provenance, shared event quality.
- Both allowed automatic fix cycles have been used.
- Final re-review job `722a36d3-d226-458f-9a85-1148da7b0bdc`: FAIL, one blocking finding.
- `server/src/refract/backends/pi.py:261–278`: repeated no-ID `turn_end` opens another implicit turn. Sequence `turn_start → message_end → turn_end → turn_end` doubles 100 input tokens to 200.
- Fix required: retain completed turn identity until a real new-turn boundary; add repeated terminal-event regression coverage.
- Review left server files unchanged at `385256099d321c768ff7b4b8fb03345cade60850`.
- Retryable review routing failures used the returned next-target token; successful reviewer was independent.
- Automatic fix bound exhausted. User authorization required before another cycle.

## Review Result

- Spec Status: FAIL
- Quality Status: FAIL
- Phase outcome: BLOCKED
- Debt: none. The correctness blocker cannot be accepted as debt.
- Remaining phases: 3 and 4 unstarted.
- Next: obtain authorization for an additional Phase 2 fix/review cycle.

## Final Checkpoint

- Phase base ref: refs/plans/worker-job-telemetry/phase-02/base
- Phase implementation ref: not written, review failed
- Plan commit ref: pending
- State checkpoint: temporary commit

Phase refs retain review evidence after checkpoint consolidation. The plan ref
names the sole commit retained on the branch.
