<!-- ccg-shared-version: 7.3.0 -->

# Phase 2 — Decision Notes

<!--
Worker Notes template. Append one `## Task <M>` block per task. Keep the file;
never overwrite earlier task blocks. Empty sub-sections = `- none`. Every task
gets a block even if all `none`.
-->

## Task 1

### Decisions made
- Added `ProfileDeclaration` for normalized raw provenance.

### Spec deviations
- none

### Tradeoffs accepted
- Workflow declarations store normalized `TargetSelection` values.

### Assumptions
- Unknown workflow names remain valid for future workflows.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: New inheritance tests initially failed because `extends` was parsed as a workflow; `python -m pytest tests/test_config.py tests/test_planning.py` passed with 25 tests after parsing was separated.

## Task 2

### Decisions made
- Chain resolution uses a local memo and visiting stack.

### Spec deviations
- none

### Tradeoffs accepted
- Resolved maps remain ordinary copied dictionaries for compatibility.

### Assumptions
- A closed cycle is reported from its first repeated profile.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Declaration-order, unknown-parent, and cycle tests failed before resolution existed; the focused config suite passed with 25 tests after lazy resolution.

## Task 3

### Decisions made
- Removed load-time built-in workflow completeness checks.

### Spec deviations
- none

### Tradeoffs accepted
- Empty profiles still require either `extends` or a workflow.

### Assumptions
- `resolve_execution_plan` remains the single unmapped-workflow rejection point.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Partial-profile and plan-resolution tests passed in `python -m pytest tests/test_config.py tests/test_planning.py`, with 32 tests collected.

## Task 4

### Decisions made
- Project declarations overlay base declarations while base resolved maps act as snapshots.

### Spec deviations
- none

### Tradeoffs accepted
- Project resolution only memoizes project declarations; base maps are copied on use.

### Assumptions
- A same-name project self-parent uses the shadowed base snapshot only when it exists.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Replacement, cross-layer inheritance, self-extension, cycle, and base immutability tests passed in the focused config suite.

## Task 5

### Decisions made
- Dashboard serialization reads raw declarations directly when provenance exists.

### Spec deviations
- none

### Tradeoffs accepted
- Programmatically constructed configs without declarations retain resolved-map fallback serialization.

### Assumptions
- Blank dashboard parent input means no `extends` key.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Dashboard declaration and unchanged GET-to-PUT tests passed with `python -m pytest tests/test_dashboard.py tests/test_config.py tests/test_planning.py tests/test_smoke.py`, 87 tests passed.

## Task 6

### Decisions made
- Project self-parent resolution now requires a base snapshot.

### Spec deviations
- none

### Tradeoffs accepted
- Global self-parent declarations still recurse to produce cycle diagnostics.

### Assumptions
- Project child references prefer project declarations over base snapshots.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Missing-base project self-extends initially reported `missing -> missing`; after the targeted branch fix, `python -m pytest tests/test_config.py tests/test_planning.py` passed 36 tests and the full suite passed 128 tests.
