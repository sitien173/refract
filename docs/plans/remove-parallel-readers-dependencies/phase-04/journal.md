<!-- refract-shared-version: 1.2.0 -->

# Phase 4 — Journal: Remove readers and dependencies from the dashboard

## META

- Plan: docs/plans/remove-parallel-readers-dependencies/PLAN.md
- Implementation Profile: google
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: 38ae1612-3953-40a2-876c-8fd8ed2c4afa
- Review Job: 3d96bf15-70a5-4a12-9824-f21a70cab9b5 PASS_WITH_DEBT, debt resolved in bd7006a
- Started: 2026-10-22T18:48:00+07:00
- Finished: 2026-10-22T18:56:00+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase 4 / Started 2026-10-22T18:48:00+07:00 / Finished 2026-10-22T18:56:00+07:00 / Plan dir docs/plans/remove-parallel-readers-dependencies
## SUMMARY
Removed reader capacity and dependency UI from dashboard.
## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modified | server/web/src/api.js | Removed updateMaxProjectReaders helper |
| Modified | server/web/src/api.test.js | Removed updateMaxProjectReaders test |
| Modified | server/web/src/App.test.jsx | Removed reader capacity form tests and mock data |
| Modified | server/web/src/components/JobDetails.jsx | Removed admission mode, dependencies, and waiting rows |
| Modified | server/web/src/components/JobDetails.test.jsx | Removed admission mode, dependencies, and waiting assertions |
| Modified | server/web/src/screens/Jobs.jsx | Removed admission mode, dependencies, and waiting columns |
| Modified | server/web/src/screens/Jobs.test.jsx | Removed dependency assertions in concatenated history test |
| Modified | server/web/src/screens/ProjectDetail.jsx | Removed admission mode, dependencies, and waiting columns |
| Modified | server/web/src/screens/ProjectDetail.test.jsx | Removed dependency assertions in jobs table filter test |
| Modified | server/web/src/screens/RuntimeSettings.jsx | Removed reader capacity form and knownDaemonKeys entry |
| Modified | server/src/refract/dashboard_static/** | Rebuilt static bundle assets via npm run build |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-04/notes.md | Appended Task 1, 2, and 3 notes and evidence |
| Modified | docs/plans/remove-parallel-readers-dependencies/phase-04/journal.md | Appended implementation response |
## NOTES
- phase-04/notes.md (## Task 1, ## Task 2, ## Task 3)
## SPEC COMPLIANCE
- Meets Spec? YES: All Done When checks pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Review Response

<!-- Coordinator appends the independent review response here. -->

## Coordinator Evidence

- Job 38ae1612 TASK_COMPLETE.
- Fresh checks: vitest 3 runs 0/202 failed; npm run build reproduced dashboard_static byte for byte; pytest tests/test_dashboard.py 45 passed; residue rg in server/web/src and dashboard_static empty; git diff --check clean.
- Deleted tests: two reader-form tests in App.test.jsx and one settings-mutation test in api.test.js, reader-only per review.
- Review 3d96bf15 PASS_WITH_DEBT: Low, unused fireEvent and waitFor imports in App.test.jsx. Coordinator removed them in bd7006a; App.test.jsx 5 passed. No debt carried.
