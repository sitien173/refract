# Phase 1 - Decision Notes

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
- RED -> GREEN: Updated fixed-workflow and MCP discovery tests failed before implementation, then passed with `uv run pytest tests/test_workflows.py tests/test_server.py::test_workflows_resource_discovers_other tests/test_server.py::test_doctor_instructions_do_not_claim_git_ownership -q`.

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- Existing partial-profile behavior remains unchanged.

### Assumptions
- Profile mappings already accept every validated workflow name.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added explicit `other` mapping and unmapped partial-profile coverage; focused configuration and planning tests pass.

## Task 3

### Decisions made
- Reused existing plan and context persistence paths.

### Spec deviations
- none

### Tradeoffs accepted
- Test helper balanced profiles now map all four workflows.

### Assumptions
- `other` uses ordinary execution and context-role handling.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Plan round-trip, job execution, and context-role tests failed on missing helper routing, then passed after adding the explicit mapping.

## Task 4

### Decisions made
- Documented `other` beside the existing built-ins.
- Reused the existing `forge-primary` target in the sample profile.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Doctor guidance should describe all four mappings uniformly.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Documentation and doctor assertions now expose the four-workflow contract; stale phrase search returns no matches.

## Task 5

### Decisions made
- Corrected only the built-in and discovery ordering.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- JSON discovery remains an array while its test compares the required tuple order.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Updated order assertions failed before the production tuple change, then passed with `uv run pytest tests/test_workflows.py::test_fixed_workflows_are_validated_strings tests/test_server.py::test_workflows_resource_discovers_other -q`.
