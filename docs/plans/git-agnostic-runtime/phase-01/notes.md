<!-- ccg-shared-version: 7.4.0 -->

# Phase 1 — Decision Notes

<!--
Append one `## Task <M>` block per task. Keep earlier task blocks.
Empty sub-sections use `- none`.
-->

## Task 1

### Decisions made
- Resolve and persist the supplied directory directly.
- Preserve the empty alias guard and duplicate constraints.

### Spec deviations
- none

### Tradeoffs accepted
- Missing and non-directory paths share the existing error wording.

### Assumptions
- Database project columns remain compatibility placeholders.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New registration tests initially failed on Git inspection. After direct directory validation, 3 focused tests passed.

## Task 2

### Decisions made
- Start jobs with an empty base commit.
- Finish successful jobs with an empty result commit.
- Leave all backend filesystem changes untouched.

### Spec deviations
- none

### Tradeoffs accepted
- Existing commit-message persistence remains unused compatibility state.

### Assumptions
- Workflow execution remains selected by the immutable execution plan.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Dirty, mutating, and failure lifecycle tests first failed under Git checks. The four focused replacements passed after removing those checks and mutations.

## Task 3

### Decisions made
- Interrupt active jobs without recovery reset.
- Remove repository inspection from server directory resolution.
- Delete the repository implementation and its dedicated tests.

### Spec deviations
- none

### Tradeoffs accepted
- Git-backed fixtures remain useful for filesystem preservation assertions.

### Assumptions
- Client-owned cleanup handles interrupted worktrees.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Plain-directory server resolution initially failed through Git inspection. Focused project-root and interruption tests passed after removal.

## Task 4

### Decisions made
- Doctor reports home, logging, and backend prerequisites only.
- Doctor always succeeds after valid configuration loading.
- Rename scheduler logging from recovered jobs to interrupted jobs.

### Spec deviations
- none

### Tradeoffs accepted
- Backend executable checks still use the existing provider lookup.

### Assumptions
- Provider-specific repository rules remain outside this phase.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Doctor payload test initially found the Git field. The doctor test passed after removing payload, logging, and exit-condition Git handling.

## Task 5

### Decisions made
- Replace commit, reset, detached-head, and read-only mutation assertions.
- Add missing-path, file-path, shutdown-interruption, and no-Git-spawn coverage.

### Spec deviations
- none

### Tradeoffs accepted
- Tests still use Git fixtures where they verify OpenMCP leaves files unchanged.

### Assumptions
- No-Git-spawn coverage can use plain directories and fake drivers.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Replacement lifecycle tests passed; the required suite passed 49 tests. Full suite passed 132 tests, with 2 live tests deselected.
