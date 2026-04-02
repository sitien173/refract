---
name: executing-plans
description: Execute a short plan one bounded task at a time with explicit worker ownership and verification. Use after planning is complete and implementation is ready to begin.
---

# Executing Plans

## Execution loop

1. Pick the next bounded task.
2. Emit a compact CP1 assessment if implementation is beginning.
3. Route the task to the correct worker or keep it local if it is truly trivial.
4. Integrate the returned diff or resolve the blocking questions.
5. Run the verification command for that task.
6. Move to the next bounded task only after the current one is stable.

## Reporting

- Keep progress updates short.
- Track only the active task, owner, and verification state.
- Do not duplicate the full plan in every update.

## Completion

- Run final verification.
- Emit a compact CP3 assessment.
- Report remaining risks or gaps if verification is partial.
