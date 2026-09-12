<!-- ccg-shared-version: 10.6.0 -->

# Phase 2 — Decision Notes

<!-- Worker appends one Task block per prompt task. -->

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: focused baseline passed (77 passed across 4 files in 7.07s). Existing React act(...) warnings remain unaddressed as baseline noise.
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED confirmed with 3 failures in src/hooks/useJobStream.test.jsx. reduceTranscriptEvents missing role/contentType metadata, reasoning summary handling, and command classification.
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN confirmed in src/hooks/useJobStream.test.jsx (27 passed). Implemented role/contentType assignment, assistant.reasoning_summary.delta merging into thinking items, exact command activity handling, and tool_call defaulting.
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED confirmed on JobDetails test. .transcript-user-card not rendered because submittedPrompt is not yet wired to JobTranscript.
- Root cause (bugfix only): n/a

## Task 5

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED confirmed with 3 failures in src/components/JobTranscript.test.jsx. Filter groups, default selections, and User card not yet implemented.
- Root cause (bugfix only): n/a

## Task 6

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED confirmed with 3 additional failures in src/components/JobTranscript.test.jsx. Thinking card, Command disclosures, and Reset filters not yet implemented.
- Root cause (bugfix only): n/a

## Task 7

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED confirmed with 3 additional failures in src/components/JobTranscript.test.jsx. Pre-virtualization filtering, remeasuring, and follow-live pause preservation not yet implemented.
- Root cause (bugfix only): n/a

## Task 8

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: RED confirmed with 1 failure in src/integration/dashboard-flow.test.jsx. End-to-end integration lacks transcript User card and filter controls.
- Root cause (bugfix only): n/a

## Task 9

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN confirmed across all 4 focused test files (93 passed). Implemented submittedPrompt forwarding, native filter fieldsets, User/Text card, Thinking card, Command disclosures, empty state, and styles.
- Root cause (bugfix only): n/a

## Task 10

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: GREEN confirmed. Worker focused suite passed with 93 tests. Worker `git diff --check` passed.
- Coordinator regression: reasoning summaries sharing `entity_id` but using different `parent_entity_id` values incorrectly merged into one item.
- Coordinator RED: the new parent-separation reducer test failed with one item instead of two.
- Coordinator GREEN: summary matching now includes `parent_entity_id`. Virtual row keys also include it. The affected reducer and transcript suites passed with 65 tests.
- Final focused verification: 94 tests passed across the four Phase 2 files.
- Final complete verification: 196 tests passed across 18 files. One preceding run exposed a transient existing Targets test failure. The isolated Targets suite passed with 13 tests, then the complete rerun passed.
- Final scoped `git diff --check` passed.
- Exact staged snapshot verification passed 91 tests across four files. Earlier Prompt Details and missing-payload UX changes remained unstaged.
- Existing React `act(...)` warnings remain baseline noise.
- Root cause: summary identity previously used only `entity_id`, ignoring its parent message identity.
