<!-- ccg-shared-version: 10.1.0 -->

# Phase 4 — Journal: Materialize codex context files

## META

- Plan: docs/plans/project-context-instructions/PLAN.md
- Implementation Profile: deepseek
- Consultation Profile: consult
- Review Profile: review
- Implementation Job: f466b417-dbd8-4b28-9780-dc81bed96040; fix a759bcda-fe25-4645-a520-523c65417c1b
- Review Job: a5ed89c2-ece0-47f5-8cb7-8b37968be276; 1d6a294f-3eb1-4bc1-9cff-48e19424ffba; 36f610a5-9e83-4f4f-a772-6b754325ea23; abcaf163-6fb4-4e81-9d26-9449fab712b8
- Started: 2026-08-28T18:51:17+07:00
- Finished: 2026-08-28T20:40:17+07:00

## Implementation Response

## Fix — FINAL remediation: Git index lock + secret quarantine trash

Replaced the uncloseable same-uid pathname design:

1. `_IndexLock` acquires the actual per-worktree Git `index.lock` with
   `O_CREAT|O_EXCL` (resolved via `git rev-parse --git-path index.lock`)
   before the final tracked check and any relocation or fresh write. Bounded
   retries; a foreign lock is never removed; release unlinks only when the
   path identity matches the held descriptor. `git add` fails while held;
   tracked check plus materialization are mutually exclusive with Git index
   mutations.
2. `_Quarantine` uses `secrets.token_hex` names in a 0700 trash directory
   (Git common storage, excluded worktree fallback). Destinations reserved
   with `O_CREAT|O_EXCL`; `os.rename` overwrites only the reservation.
   Payloads are never deleted. Managed files leave the target absent with
   bytes preserved; foreign/tracked swaps are restored with no-overwrite link
   or preserved-and-logged on race loss.
3. Cleanup and sweep leave target paths absent without pathname payload
   deletion; no predictable names; no pruning.
4. Direct tests cover lock blocking, foreign-lock preservation, release on
   exits, quarantine-name preservation, swapped-byte recoverability, and
   target-path disappearance for managed cleanup.

`uv run pytest tests/test_context_files.py tests/test_execution.py` -> 92
passed; `uv run pytest` -> 262 passed, 4 failed (pre-existing `job_wait` set),
3 deselected.

# EXTERNAL RESPONSE (final)
## META
- Phase / Started / Finished / Plan dir
- 4 / 2026-08-28T18:51:17+07:00 / 2026-08-28T20:40:17+07:00 / docs/plans/project-context-instructions/phase-04
## SUMMARY
Materialized codex instructions as Git-invisible composed `AGENTS.override.md` files per attempt with synchronous marker-scoped cleanup, startup sweeping, and fail-closed refusal of tracked/foreign/symlink/hardlink/directory targets, with per-worktree Git index locking and secret-quarantine trash.
## FILES MODIFIED
| Action | Path | Change |
| Create | src/openmcp/context_files.py | Managed marker, scrubbed Git calls, tracked check, anchored exclude-block writer via `$GIT_COMMON_DIR/info/exclude`, materialize/cleanup/sweep helpers; final remediation: per-worktree Git `index.lock` acquisition (`O_CREAT|O_EXCL`, bounded retries, identity-checked release), secret `token_hex` quarantine trash (0700, Git common storage + excluded fallback), no-overwrite restore, no pathname payload deletion, no pruning |
| Modify | src/openmcp/execution.py | Per-attempt codex materialization, REQUEST_FATAL on refusal, synchronous cleanup in finally + driver-exception path |
| Modify | src/openmcp/runtime.py | Startup sweep of marker-bearing leftovers per registered project |
| Create | tests/test_context_files.py | 43 tests: composition, Git-invisibility main+linked worktree, exclusion once, refusals, leftover overwrite, cleanup/sweep quarantine, index-lock blocking + foreign-lock preservation + release-on-exit, secret quarantine names, swapped-bytes recoverability, target-path disappearance |
| Modify | tests/test_execution.py | 13 tests: materialize/cleanup on success/failure/timeout/cancellation/driver-exception, REQUEST_FATAL, non-Git warning, startup sweep |
| Modify | docs/plans/project-context-instructions/phase-04/notes.md | Per-task decision notes + fix blocks with RED→GREEN evidence |
| Modify | docs/plans/project-context-instructions/phase-04/journal.md | META Finished + final remediation notes + EXTERNAL RESPONSE appended |
## NOTES
- phase-04/notes.md (## Task 1, ## Task 2, ## Task 3, ## Fix — Pre-commit defect correction, ## Fix — Review finding: inode-safe replacement (HIGH), ## Fix — Review cycle 2: inode-bound replacement and quarantine cleanup (HIGH), ## Fix — FINAL remediation: Git index lock + secret quarantine trash (consultation))
## SPEC COMPLIANCE
- Meets Spec? YES — consultation remediation complete: per-worktree index.lock mutual exclusion, secret quarantine trash with no-overwrite restore, target paths absent for managed cleanup without payload deletion, all direct tests green; only the 4 pre-existing `job_wait` timeout failures remain (present on base commit, out of scope).
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW
- Status: PASS
- Findings: None
- Scope checked: src/openmcp/context_files.py, tests/test_context_files.py

## Review Result

- Spec Status: PASS
- Debt: none

## Final Commit

- Implementation: cf151df; fixes acd1b2d, 2b40b02, 30d4512
- State record: this journal update's commit
