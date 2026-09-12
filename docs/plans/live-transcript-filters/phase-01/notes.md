<!-- ccg-shared-version: 10.6.0 -->

# Phase 1 — Decision Notes

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
- RED -> GREEN: baseline suite passed (85 passed in 13.14s). Uncommitted Agy protocol changes and tests inspected and verified intact.
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
- RED -> GREEN: RED confirmed with 7 failures in tests/test_streaming_backends.py. Missing activity key on tool.started events for Claude, Codex, Pi, and Agy.
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
- RED -> GREEN: RED confirmed on test_exact_command_classification_and_unsafe_substring_rejection. KeyError 'activity' when verifying exact bash mapping and substring rejection across providers.
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
- RED -> GREEN: GREEN confirmed on test_negative_reasoning_and_diagnostics_excluded. Verified thinking deltas, generic reasoning, prompts, and diagnostics remain excluded from normalized events across all backends.
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
- RED -> GREEN: RED confirmed with 3 failures in tests/test_streaming.py. StreamRecorder does not yet coalesce, split at 8KiB UTF-8, or discard extra fields for assistant.reasoning_summary.delta.
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
- RED -> GREEN: RED confirmed on test_execution_all_provider_fixtures_persistence_and_authoritative_results. Missing activity field in persisted tool.started stream events.
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
- RED -> GREEN: GREEN confirmed on test_classify_tool_activity_unit. Implemented classify_tool_activity in src/openmcp/backends/__init__.py with exact case-sensitive allow-list for claude and codex bash tools.
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
- RED -> GREEN: GREEN confirmed across tests/test_streaming_backends.py (16 passed) and tests/test_execution.py (58 passed). Added activity classification to tool.started events for Claude, Codex, Pi, and Agy.
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
- RED -> GREEN: GREEN confirmed across tests/test_streaming.py (20 passed). Extended StreamRecorder to support assistant.reasoning_summary.delta with same-kind coalescing, UTF-8 splitting, and extra field exclusion.
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
- RED -> GREEN: GREEN confirmed. Ran Done When verification suite (94 passed in 12.67s). git diff --check passed with zero errors across all modified Phase 1 files.
- Root cause (bugfix only): n/a
