# Phase 2 — Journal: Remove capabilities from public surfaces

## META

- Plan: docs/plans/workflow-capability-simplification/PLAN.md
- Implementation Profile: openai_impl
- Consultation Profile: n/a
- Review Profile: review
- Implementation Job: d5514957-4e0d-4083-ae7c-cdb214027596
- Review Job: pending
- Started: 2026-07-28T01:10:57+07:00
- Finished: 2026-07-28T01:16:48+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: 2 / Started: 2026-07-28T01:10:57+07:00 / Finished: 2026-07-28T01:16:48+07:00 / Plan dir: docs/plans/workflow-capability-simplification/phase-02
## SUMMARY
Removed capability fields from public Python, dashboard, React, configuration, and documentation surfaces.
## FILES MODIFIED
| Action | Path | Change |
| Modify | src/openmcp/models.py | Removed capabilities from TargetView. |
| Modify | src/openmcp/execution.py | Removed capabilities from target responses. |
| Modify | src/openmcp/dashboard.py | Removed capabilities from dashboard config responses. |
| Modify | src/openmcp/config_writer.py | Stripped legacy capability keys during writes. |
| Modify | web/src/lib/types.ts | Removed capabilities from Target. |
| Modify | web/src/lib/api.test.ts | Updated target response fixture. |
| Modify | web/src/views/Targets.tsx | Removed the capabilities column. |
| Modify | web/src/views/Targets.test.tsx | Updated target view fixtures and assertions. |
| Modify | web/src/views/Overview.test.tsx | Updated target fixtures. |
| Modify | tests/test_server.py | Asserted the public target model omits capabilities. |
| Modify | tests/test_dashboard.py | Covered response removal and config cleanup. |
| Modify | README.md | Removed capability configuration and guidance. |
| Modify | src/openmcp/dashboard_static/index.html | Updated generated asset references. |
| Delete | src/openmcp/dashboard_static/assets/index-D6gyV-9_.js | Removed stale dashboard bundle. |
| Add | src/openmcp/dashboard_static/assets/index-CSlrrhcl.js | Added regenerated dashboard bundle. |
| Modify | docs/plans/workflow-capability-simplification/phase-02/notes.md | Recorded task decisions and evidence. |
| Modify | docs/plans/workflow-capability-simplification/phase-02/journal.md | Recorded the implementation response. |
## NOTES
- phase-02/notes.md  (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES  — Python, web, build, and packaging checks pass.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

## Review Result

- Spec Status: PENDING
- Debt: none

## Final Commit

- Implementation: pending
- State record: this journal update's commit
