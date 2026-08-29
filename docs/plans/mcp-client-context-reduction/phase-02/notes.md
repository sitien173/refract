<!-- ccg-shared-version: 10.1.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Reduced the documented resource surface to six templates.
- Added `context_init` as the eighth tool.
- Documented bounded jobs reconciliation and identity omission.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The OpenMCP daemon restarts before clients consume templates.

### Follow-ups for human
- none

### Test evidence
- Tool table contains 8 rows.
- Resource list contains 6 entries.

## Task 2

### Decisions made
- Moved Gate 3 procedures into `references/review.md`.
- Retained both required output blocks and safety rules.

### Spec deviations
- Compressed Session Resume Key wording to meet the byte limit while preserving its contract.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `SKILL.md` is 7662 bytes and 195 lines.
- `references/review.md` is 65 lines.

## Task 3

### Decisions made
- Documented persistent per-workflow context instructions.
- Updated executing-plans reconciliation for bounded job lists.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Provider identity contract guard passed.

## Task 4

### Decisions made
- Repointed all three debt assertions to `references/review.md`.
- Added a 100-line cap for the review reference.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `/home/ngosi/projects/superpowers-ccg/tests/run.sh` passed.
