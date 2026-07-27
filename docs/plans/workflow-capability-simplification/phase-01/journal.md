# Phase 1 — Journal: Simplify workflow and target routing

## META

- Plan: docs/plans/workflow-capability-simplification/PLAN.md
- Implementation Profile: openai_impl
- Consultation Profile: n/a
- Review Profile: review
- Implementation Jobs: e067608f-a3ff-4d93-b29c-68a43228732b, ad16cb58-5ccf-4110-aabb-a7aa21b29f2b
- Review Job: 6aa3c4b6-113f-43a5-99fc-1a56b45a45c4
- Started: 2026-07-28T00:57:27+07:00
- Finished: 2026-07-28T01:05:19+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: 1 / Started: 2026-07-28T00:57:27+07:00 / Finished: 2026-07-28T01:01:51+07:00 / Plan dir: docs/plans/workflow-capability-simplification/phase-01
## SUMMARY
Removed target capabilities from core routing and snapshots while preserving fixed workflows.
## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/config.py | Removed target capabilities and validated profile workflow keys. |
| Modify | src/openmcp/planning.py | Omitted capabilities from new plans and parsed legacy fields. |
| Modify | src/openmcp/runtime.py | Routed workflow strings directly. |
| Modify | src/openmcp/workflows.py | Replaced workflow definitions with validated strings. |
| Modify | tests/orchestration_helpers.py | Removed capability metadata from fixtures. |
| Modify | tests/test_config.py | Added unknown workflow and capability removal coverage. |
| Modify | tests/test_planning.py | Covered new and legacy plan snapshots. |
| Modify | tests/test_workflows.py | Covered validated workflow strings. |
| Modify | docs/plans/workflow-capability-simplification/phase-01/notes.md | Recorded task decisions and evidence. |
| Modify | docs/plans/workflow-capability-simplification/phase-01/journal.md | Recorded the implementation response. |
## NOTES
- phase-01/notes.md  (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES  — Fixed routing, legacy parsing, and retry coverage pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

# EXTERNAL RESPONSE
## META
- Phase: 1 / Started: 2026-07-28T01:02:00+07:00 / Finished: 2026-07-28T01:05:19+07:00 / Plan dir: docs/plans/workflow-capability-simplification/phase-01
## SUMMARY
Restored transitional capability fields with empty lists in execution and dashboard adapters.
## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/config.py | Removed target capabilities and validated profile workflow keys. |
| Modify | src/openmcp/planning.py | Omitted capabilities from new plans and parsed legacy fields. |
| Modify | src/openmcp/runtime.py | Routed workflow strings directly. |
| Modify | src/openmcp/workflows.py | Replaced workflow definitions with validated strings. |
| Modify | src/openmcp/execution.py | Returned empty capabilities in target views. |
| Modify | src/openmcp/dashboard.py | Returned empty capabilities in config responses. |
| Modify | tests/orchestration_helpers.py | Removed capability metadata from fixtures. |
| Modify | tests/test_config.py | Added unknown workflow and capability removal coverage. |
| Modify | tests/test_planning.py | Covered new and legacy plan snapshots. |
| Modify | tests/test_workflows.py | Covered validated workflow strings. |
| Modify | docs/plans/workflow-capability-simplification/phase-01/notes.md | Recorded task decisions and evidence. |
| Modify | docs/plans/workflow-capability-simplification/phase-01/journal.md | Recorded the fix response. |
## NOTES
- phase-01/notes.md  (## Task 5)
## SPEC COMPLIANCE
- Meets Spec? YES  — Focused, dashboard, and full Python suites pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW

- Status: **PASS**
- Findings: None.
- Scope checked: `workflows.py`, `config.py`, `planning.py`, `runtime.py`,
  `execution.py`, `dashboard.py`, and scoped tests.

Evidence: fixed workflow validation remains; unknown profile workflow keys
reject; legacy capability fields are ignored while persisted-plan parsing
remains compatible; `TargetView` and dashboard retain empty capability lists.

- Spec Status: PASS
- Debt: none

## Final Commit

- Implementation: 318aad0
- State record: this journal update's commit
