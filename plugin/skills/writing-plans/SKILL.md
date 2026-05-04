---
name: writing-plans
description: "Creates implementation plans made of executable phases with 2-4 related tasks, explicit owners, file sets, acceptance criteria, reviewer checklists, and integration checks. Use when turning a confirmed design into a phase-based implementation plan."
---

# Writing Plans

## Use When

- User confirms a design and wants an implementation plan.
- Work needs phase boundaries before execution.
- A plan must be executable by Claude, Codex, or Gemini one phase at a time.

## Workflow

1. Read only the design docs and code context needed to scope phases.
2. Break work into coarse implementation phases, not tiny task lists.
3. Put 2-4 related implementation tasks in each phase.
4. Assign one owner per phase: `codex`, `gemini`, or `claude`.
5. Include file set, acceptance criteria, reviewer checklist, and integration checks for every phase.
6. Add routing notes only when the phase owner is `gemini` or `claude`.
7. Save the plan, then offer same-session execution with `executing-phases` or dedicated execution with `executing-plans`.

## Hard Rules

- Default owner is `codex` for most implementation.
- Use `gemini` only for UI-heavy visual phases.
- Use `claude` only for orchestration, review, docs, clarification, or when the user overrides routing.
- Use `cross-validation` only for architecture or genuine multi-domain conflicts.
- Do not create two-pass tasks where one worker drafts code and Claude re-implements it.

## References

- `skills/coordinating-multi-model-work/routing-decision.md` — owner and route selection.
- `skills/coordinating-multi-model-work/checkpoints.md` — checkpoint and phase requirements.
- `skills/shared/protocol-threshold.md` — exact CP response blocks.

## Phase Shape

```markdown
### Phase N: [Short outcome]

**Owner:** `codex` | `gemini` | `claude`

**Goal:** [One clear outcome for this phase]

**Files:**
- Modify: `path/to/file`
- Create: `path/to/file`

**Tasks:**
1. [related implementation task]
2. [related implementation task]
3. [optional related implementation task]
4. [optional related implementation task]

**Acceptance Criteria:**
- [criterion]

**Reviewer Checklist:**
- [spec requirement]
- [edge case / regression risk]
- [verification expectation]

**Integration Checks:**
- `exact command`
```
