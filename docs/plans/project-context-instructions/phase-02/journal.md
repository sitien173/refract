<!-- ccg-shared-version: 10.1.0 -->

# Phase 2 — Journal: Snapshot instructions into execution plans

## META

- Plan: docs/plans/project-context-instructions/PLAN.md
- Implementation Profile: deepseek
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 10d11c2e-78e0-4d11-882f-688657b0b479
- Review Job: n/a
- Started: 2026-08-28T18:06:48+07:00
- Finished: 2026-08-28T18:40:07+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir
- 2 / 2026-08-28T18:06:48+07:00 / 2026-08-28T18:40:07+07:00 / docs/plans/project-context-instructions/phase-02
## SUMMARY
Snapshotted each stored project/workflow instruction into the immutable per-job execution plan at submission, with backward-compatible parsing and unchanged target keys.
## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/planning.py | `ExecutionPlan.instruction` field, `execution_plan_data` emits it, `parse_execution_plan` defaults missing key to `""` and rejects non-string, `resolve_execution_plan` accepts optional `instruction` |
| Modify | src/openmcp/runtime.py | `Runtime.submit` reads stored instruction via `database.context_instruction` and passes it into the resolved plan |
| Modify | tests/test_planning.py | Round-trip, legacy default-empty, non-string rejection, target key stability tests |
| Modify | tests/test_server.py | Submission snapshot, empty-instruction snapshot, and post-submit immutability tests |
| Modify | docs/plans/project-context-instructions/phase-02/notes.md | Per-task decision notes with RED→GREEN evidence |
| Modify | docs/plans/project-context-instructions/phase-02/journal.md | META Finished + full EXTERNAL RESPONSE appended |
## NOTES
- phase-02/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES — all Done When checks pass; 10 new tests green; only the 4 pre-existing `job_wait` timeout failures remain (present on base commit, out of scope).
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

## Review Result

- Spec Status: PENDING
- Debt: none

## Final Commit

- Implementation: pending
- State record: this journal update's commit
