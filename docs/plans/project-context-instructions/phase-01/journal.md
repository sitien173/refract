<!-- ccg-shared-version: 10.1.0 -->

# Phase 1 — Journal: Store project context instructions

## META

- Plan: docs/plans/project-context-instructions/PLAN.md
- Implementation Profile: deepseek
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 26ee16a3-c50f-4aba-b795-12fb7633b9ad
- Review Job: 067719ca-6d50-4fbd-9701-f9f4af8eb0ce
- Started: 2026-08-28T17:48:55+07:00
- Finished: 2026-08-28T18:03:39+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir
- 1 / 2026-08-28T17:48:55+07:00 / 2026-08-28T18:03:39+07:00 / docs/plans/project-context-instructions/phase-01
## SUMMARY
Stored and exposed durable per-project, per-workflow context instructions via schema version 7, `context_init`, and the context_instructions resource, with no job-execution changes.
## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/database.py | Schema v7: `context_instructions` table (FK cascade on projects), v6/v5/legacy migrations bump to 7, `set_context_instruction`/`context_instruction`/`context_instructions` ops |
| Modify | src/openmcp/models.py | `ContextInstructionsResult` model |
| Modify | src/openmcp/runtime.py | `Runtime.set_context_instruction` and `Runtime.context_instructions` with project/workflow validation |
| Modify | src/openmcp/server.py | `context_init` MCP tool and `openmcp://projects/{project_id}/context_instructions` resource |
| Modify | tests/test_database.py | v7 fresh/migration/reopen tests, v6/v5 migration preservation, round-trip/clear/cascade/FK tests |
| Modify | tests/test_server.py | `context_init` tool/resource contract and behavior tests |
| Modify | docs/plans/project-context-instructions/phase-01/notes.md | Per-task decision notes with RED→GREEN evidence |
| Modify | docs/plans/project-context-instructions/phase-01/journal.md | META Finished + full EXTERNAL RESPONSE appended |
## NOTES
- phase-01/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES — all Done When checks pass; 14 new tests green; only the 4 pre-existing `job_wait` timeout failures remain (present on base commit, out of scope).
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW
- Status: PASS
- Findings: None
- Scope checked: src/openmcp/database.py, src/openmcp/models.py, src/openmcp/runtime.py, src/openmcp/server.py, tests/test_database.py, tests/test_server.py

## Review Result

- Spec Status: PASS
- Debt: none

## Final Commit

- Implementation: fc752a6
- State record: this journal update's commit
