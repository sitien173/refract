<!-- ccg-shared-version: 10.1.0 -->

# Phase 4 — Journal: Materialize codex context files

## META

- Plan: docs/plans/project-context-instructions/PLAN.md
- Implementation Profile: deepseek
- Consultation Profile: consult
- Review Profile: review
- Implementation Job: f466b417-dbd8-4b28-9780-dc81bed96040; fix a759bcda-fe25-4645-a520-523c65417c1b
- Review Job: n/a
- Started: 2026-08-28T18:51:17+07:00
- Finished: 2026-08-28T19:30:01+07:00

## Implementation Response

## Fix — Pre-commit defect correction

Defect 1: `materialize_context_file` replaced the project root with the Git
Top-level before composition, so a project rooted in a repository subdirectory
inlined the wrong `AGENTS.md`. Fixed by preserving the supplied project root
(`project_root`) for composition and the "nothing to deliver" check; the Git
Top-level is used only for index and exclusion operations.

Defect 2: non-Git roots skipped `_refuse_existing_target`, then the
leftover-overwrite unlink could remove a foreign file. Fixed by applying
identical symlink, directory, hardlink, and foreign-file refusal before any
replacement in both Git and non-Git projects.

8 regression tests added; `uv run pytest tests/test_context_files.py
tests/test_execution.py` -> 79 passed; `uv run pytest` -> 249 passed, 4 failed
(pre-existing `job_wait` set), 3 deselected.

# EXTERNAL RESPONSE (revised)
## META
- Phase / Started / Finished / Plan dir
- 4 / 2026-08-28T18:51:17+07:00 / 2026-08-28T19:30:01+07:00 / docs/plans/project-context-instructions/phase-04
## SUMMARY
Materialized codex instructions as Git-invisible composed `AGENTS.override.md` files per attempt with synchronous marker-scoped cleanup, startup sweeping, and fail-closed refusal of tracked/foreign/symlink/hardlink/directory targets.
## FILES MODIFIED
| Action | Path | Change |
| Create | src/openmcp/context_files.py | Managed marker, scrubbed Git calls, tracked check, anchored exclude-block writer via `$GIT_COMMON_DIR/info/exclude`, materialize/cleanup/sweep helpers; fix: project root preserved for composition, identical refusal in Git and non-Git projects |
| Modify | src/openmcp/execution.py | Per-attempt codex materialization, REQUEST_FATAL on refusal, synchronous cleanup in finally + driver-exception path |
| Modify | src/openmcp/runtime.py | Startup sweep of marker-bearing leftovers per registered project |
| Create | tests/test_context_files.py | 30 tests: composition (incl. repo-subdirectory project root), Git-invisibility main+linked worktree, exclusion once, tracked/foreign/symlink/hardlink/dir refusals (Git and non-Git), leftover overwrite, cleanup, sweep |
| Modify | tests/test_execution.py | 13 tests: materialize/cleanup on success/failure/timeout/cancellation/driver-exception, REQUEST_FATAL, non-Git warning, startup sweep |
| Modify | docs/plans/project-context-instructions/phase-04/notes.md | Per-task decision notes + pre-commit fix block with RED→GREEN evidence |
| Modify | docs/plans/project-context-instructions/phase-04/journal.md | META Finished + fix note + revised EXTERNAL RESPONSE appended |
## NOTES
- phase-04/notes.md (## Task 1, ## Task 2, ## Task 3, ## Fix — Pre-commit defect correction)
## SPEC COMPLIANCE
- Meets Spec? YES — both defects fixed with regression tests; 43 new tests green; only the 4 pre-existing `job_wait` timeout failures remain (present on base commit, out of scope).
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
