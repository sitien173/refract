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
- RED -> GREEN: Updated workflow test failed against WorkflowDefinition; targeted suite passed after validated strings replaced the definitions.

## Task 2

### Decisions made
- Removed capability storage and capability-based target rejection.

### Spec deviations
- none

### Tradeoffs accepted
- Legacy TOML capability keys remain ignored and loadable.

### Assumptions
- Phase 2 owns public target capability surfaces.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Capability removal test failed while TargetConfig still exposed the field; `uv run pytest tests/test_config.py -q` passed with 36 tests.

## Task 3

### Decisions made
- Legacy snapshot capability keys are ignored during parsing.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Serialized target fields otherwise retain their existing coercion rules.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Snapshot tests failed when serialization accessed removed capabilities; targeted workflow, config, planning, and execution suite passed with 59 tests.

## Task 4

### Decisions made
- Profile workflow keys validate through the fixed workflow registry.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `extends` remains the only non-workflow profile key.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Unknown workflow profile test initially did not raise; `uv run pytest tests/test_config.py -q` passed with 36 tests.

## Task 5

### Decisions made
- Transitional target adapters return empty capability lists.

### Spec deviations
- none

### Tradeoffs accepted
- Public capability fields remain until Phase 2.

### Assumptions
- Empty lists preserve the existing response schemas.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Dashboard tests failed five times on removed TargetConfig.capabilities; focused suite passed with 59 tests, dashboard suite passed with 27 tests, and full Python suite passed with 141 tests and 2 deselected.
