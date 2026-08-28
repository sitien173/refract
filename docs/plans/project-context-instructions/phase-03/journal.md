<!-- ccg-shared-version: 10.1.0 -->

# Phase 3 — Journal: Inject instructions into claude and pi

## META

- Plan: docs/plans/project-context-instructions/PLAN.md
- Implementation Profile: deepseek
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 8b5fce3d-6d53-4f7f-b76d-d8bc43af3579
- Review Job: 6a6905b6-fd10-449a-b978-728f33696fee
- Started: 2026-08-28T18:42:27+07:00
- Finished: 2026-08-28T18:48:02+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir
- 3 / 2026-08-28T18:42:27+07:00 / 2026-08-28T18:48:02+07:00 / docs/plans/project-context-instructions/phase-03
## SUMMARY
Injected the snapshotted instruction into claude and pi workers via `--append-system-prompt` inside each attempt, leaving agy/codex argv and empty-instruction output unchanged.
## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/drivers.py | `_target_args(target, instruction="")` appends `--append-system-prompt <instruction>` after target args for pi and claude only; `DriverRegistry.execute` accepts `instruction` |
| Modify | src/openmcp/execution.py | `TargetExecutor.execute` passes `instruction=plan.instruction` into each attempt's `drivers.execute` call |
| Modify | CLI_ARGUMENTS.md | Documented pi/claude `--append-system-prompt` injection: emitted after target args, survives `--no-context-files`/`--safe-mode`, empty adds no flag, never logged in full |
| Modify | tests/test_execution.py | Driver argv tests: claude/pi normal+isolated, agy/codex unaffected, empty-instruction identity, `_target_args` ordering, retry recompile per backend |
| Modify | docs/plans/project-context-instructions/phase-03/notes.md | Per-task decision notes with RED→GREEN evidence |
| Modify | docs/plans/project-context-instructions/phase-03/journal.md | META Finished + full EXTERNAL RESPONSE appended |
## NOTES
- phase-03/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES — all Done When checks pass; 12 new tests green; only the 4 pre-existing `job_wait` timeout failures remain (present on base commit, out of scope).
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW
- Status: PASS
- Findings: None
- Scope checked: src/openmcp/drivers.py, src/openmcp/execution.py, CLI_ARGUMENTS.md, tests/test_execution.py

## Review Result

- Spec Status: PASS
- Debt: none

## Final Commit

- Implementation: 570e632
- State record: this journal update's commit
