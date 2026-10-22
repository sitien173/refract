<!-- refract-shared-version: 1.2.0 -->

# Phase 1 — Journal: Green baseline

<!--
Phase Journal template. Copy to docs/plans/remove-parallel-readers-dependencies/phase-01/journal.md at phase
start, fill the META, then append the full `# EXTERNAL RESPONSE` block (see
erp.md) under `## Implementation Response` after all tasks. Never overwrite earlier
sections.
-->

## META

- Plan: docs/plans/remove-parallel-readers-dependencies/PLAN.md
- Implementation Profile: google
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: f8a548a4-1d8a-4b52-9a1e-213961650633
- Review Job: d9cea95e-c6c4-4545-910a-c5e23a8305d4 FAIL; 2dc5f65a-dc3f-4ea7-83f8-8d6b5e38c317 PASS
- Started: 2026-10-22T17:00:00+07:00
- Finished: 2026-10-22T18:00:00+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase 1 / Started 2026-10-22T17:00:00+07:00 / Finished 2026-10-22T17:15:00+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Repaired contract envelope assertion and resolved dashboard test flakiness.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | plugin/tests/test-contracts.sh | Added metadata to job_wait return envelope and targets_unavailable to approved_errors |
| Modified | server/web/src/integration/dashboard-flow.test.jsx | Synchronized submit clicks with button enablement and wrapped getJobOutput in waitFor |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-01/notes.md | Recorded Task 1 and Task 2 decisions, spec deviations, and root cause evidence |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-01/journal.md | Recorded implementation response |
## NOTES
- docs/plans/remove-parallel-readers-dependencies/phase-01/notes.md (## Task 1, ## Task 2)
## SPEC COMPLIANCE
- Meets Spec? YES: All phase verification checks pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

<!-- Coordinator appends the independent review response here. -->

## Review Result

- Spec Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/remove-parallel-readers-dependencies/phase-01/base
- Phase implementation ref: refs/plans/remove-parallel-readers-dependencies/phase-01/impl
- Plan commit ref: refs/plans/remove-parallel-readers-dependencies/impl or `pending`
- State checkpoint: temporary commit, or `n/a (untracked)` when plan artifacts
  are excluded

Phase refs retain review evidence after checkpoint consolidation. The plan ref
names the sole commit retained on the branch.

## Coordinator Validation

- Initial validation after f8a548a4: vitest run 1 failed 2 tests (Profiles.test.jsx, Targets.test.jsx); runs 2 and 3 passed. Spec FAIL; fix cycle 1 submitted.
- Fix job 091d3fc7 ended near the 30-minute mark with no ERP and no notes block. It edited test files only: App.test.jsx, dashboard-flow.test.jsx, Profiles.test.jsx, ProjectDetail.test.jsx, Targets.test.jsx. All inside allowed scope.
- Fresh checks after fix, load average 14.64 on 8 CPUs:
  - `bash plugin/tests/run.sh` -> exit 0
  - `npx vitest run` x3 -> 0 of 205 failed each run
  - `uv run --extra dev pytest -q` -> 578 passed, 3 deselected
  - `git diff --check` -> pass
- Diff scan: no timeout increase, retry, skip, or only. Removed assertions were moved into waitFor blocks, not deleted.

## Coordinator Evidence

- Jobs: 693da6ba no ERP; f8a548a4 TASK_COMPLETE; 091d3fc7 fix cycle 1, no ERP, validated by Coordinator.
- Review d9cea95e: FAIL, Medium: fireEvent.change inside waitFor callbacks at 12 sites.
- Fix cycle 2, Coordinator commit 348b722: each change runs once, preceded by `await waitFor(() => expect(dialog).toContainElement(document.activeElement))`. Root cause: TargetEditor and ProfileEditor reset formData in their open effect; Modal focuses the dialog from a setTimeout after effects flush. ProjectDetail create-override opens after an awaited fetch, so that test uses findByLabelText.
- Fresh checks after fix: vitest 3 runs 0/205 failed at load ~10; plugin run.sh 0; git diff --check clean; pytest 578 passed, 3 deselected at 904a6bf, no server change since.
- Review 2dc5f65a: PASS, no findings.
- Extra scope: plugin `targets_unavailable` added to the approved error set to match tool-contract.md; test files App, Profiles, ProjectDetail, Targets beyond dashboard-flow share the same root cause.
