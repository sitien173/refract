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
- Finished: 2026-08-28T19:45:10+07:00

## Implementation Response

## Fix — Review finding: inode-safe replacement (HIGH)

Replaced the pathname-based leftover overwrite with an inode-safe replacement:
`_open_managed_for_replacement` opens the existing regular single-link file
with `O_RDWR | O_NOFOLLOW`, validates the marker and link count through that
same descriptor, then `_replace_managed_file` truncates and writes through the
descriptor. The pathname is never unlinked or re-opened for mutation after
validation, so a replacement race swapping in a foreign or tracked file cannot
delete or modify it. Absent targets still use exclusive `O_EXCL` creation.
Two race regression tests added. `uv run pytest tests/test_context_files.py
tests/test_execution.py` -> 81 passed; `uv run pytest` -> 251 passed, 4 failed
(pre-existing `job_wait` set), 3 deselected.

# EXTERNAL RESPONSE (revised)
## META
- Phase / Started / Finished / Plan dir
- 4 / 2026-08-28T18:51:17+07:00 / 2026-08-28T19:45:10+07:00 / docs/plans/project-context-instructions/phase-04
## SUMMARY
Materialized codex instructions as Git-invisible composed `AGENTS.override.md` files per attempt with synchronous marker-scoped cleanup, startup sweeping, and fail-closed refusal of tracked/foreign/symlink/hardlink/directory targets, with inode-safe replacement.
## FILES MODIFIED
| Action | Path | Change |
| Create | src/openmcp/context_files.py | Managed marker, scrubbed Git calls, tracked check, anchored exclude-block writer via `$GIT_COMMON_DIR/info/exclude`, materialize/cleanup/sweep helpers; fixes: project root preserved for composition, identical refusal in Git and non-Git projects, inode-safe replacement via `O_NOFOLLOW` descriptor (no pathname unlink) |
| Modify | src/openmcp/execution.py | Per-attempt codex materialization, REQUEST_FATAL on refusal, synchronous cleanup in finally + driver-exception path |
| Modify | src/openmcp/runtime.py | Startup sweep of marker-bearing leftovers per registered project |
| Create | tests/test_context_files.py | 32 tests: composition (incl. repo-subdirectory project root), Git-invisibility main+linked worktree, exclusion once, tracked/foreign/symlink/hardlink/dir refusals (Git and non-Git), leftover overwrite, cleanup, sweep, race-swapped foreign/tracked preservation |
| Modify | tests/test_execution.py | 13 tests: materialize/cleanup on success/failure/timeout/cancellation/driver-exception, REQUEST_FATAL, non-Git warning, startup sweep |
| Modify | docs/plans/project-context-instructions/phase-04/notes.md | Per-task decision notes + fix blocks with RED→GREEN evidence |
| Modify | docs/plans/project-context-instructions/phase-04/journal.md | META Finished + fix notes + revised EXTERNAL RESPONSE appended |
## NOTES
- phase-04/notes.md (## Task 1, ## Task 2, ## Task 3, ## Fix — Pre-commit defect correction, ## Fix — Review finding: inode-safe replacement (HIGH))
## SPEC COMPLIANCE
- Meets Spec? YES — review finding fixed with inode-safe replacement and race regression tests; 45 new tests green; only the 4 pre-existing `job_wait` timeout failures remain (present on base commit, out of scope).
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
