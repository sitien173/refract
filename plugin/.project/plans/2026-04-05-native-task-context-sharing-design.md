# Native Task Management + Smart Context Sharing Integration Design

> **Date:** 2026-04-05
> **Topic:** Enhance native-task-management with smart context sharing

## Goal
Make native tasks (TaskCreate/TaskUpdate/TaskList/.tasks.json) fully compatible with smart context sharing workflow (CONTEXT_ARTIFACTS, TASK_CONTEXT_BUNDLE, deltas) so context travels with tasks across brainstorming → planning → execution and sessions without prompt bloat.

## Confirmed Design Sections
1. **Overview**: Tasks embed CONTEXT_REFS in json:metadata; executing-plans hydrates bundle.
2. **Implementation Details**: Update task-format-reference.md + skills to populate contextRefs/hydratedContext.
3. **Persistence & Flow**: .tasks.json stores per-task contextArtifacts; deltas for same-task resumes.
4. **Execution**: CP1/CP2 use extracted bundle from task; CP4 unchanged (spec-only).

## Architecture Changes
- **task-format-reference.md**: Add contextRefs, hydratedContext, contextBundle to metadata schema.
- **brainstorming/writing-plans**: Populate refs from CP0 artifacts during TaskCreate.
- **executing-plans**: On TaskList load, reconstruct bundle from task metadata or .tasks.json before CP1.
- **context-sharing.md**: Document how tasks participate in artifact storage and delta follow-ups.
- Persistence: Extend .tasks.json with context history per task ID.

## Trade-offs Considered
- **Option 1 (chosen)**: Embed refs in task metadata (lightweight, survives TaskGet).
- **Option 2**: Separate context db — rejected (YAGNI, adds complexity).
- **Option 3**: Full CP0 on every task resume — rejected (violates narrow prompts).

## Testing & Verification
- Verify metadata contains context keys via grep.
- Test resumption: create task, simulate session, check bundle hydration.
- Run skill tests for brainstorming/executing-plans.

## Next Steps
- Implement via writing-plans or executing-plans skill.
- Wire dependencies if multiple tasks created.
- Confirm with `TaskList`.

Approved via iterative sections.
