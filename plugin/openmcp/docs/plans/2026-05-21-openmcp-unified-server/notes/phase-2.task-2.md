# phase-2.task-2

## Decisions made (not in spec)
- Added explicit FastMCP tool metadata (`name` and concise description) to clarify backend dispatch and retry/SESSION_ID behavior.
- Kept backend selection simple with direct `if backend == "agy"` dispatch and defaulting to codex for the other literal branch.

## Spec deviations
- none

## Tradeoffs accepted
- Validation of retry parameter bounds is not enforced in tool code to keep behavior minimal and aligned with requested signature.

## Assumptions
- Phase 1 backend param dataclasses remain stable for direct construction in the tool adapter layer.

## Follow-ups for human
- none
