---
name: writing-plans
description: "Turns a confirmed design into a phase-based implementation plan. Each phase has 2–4 tasks, one owner, file set, acceptance criteria, and integration checks."
---

# Writing Plans

## Use When

- Design is confirmed and user wants an implementation plan.
- Work needs phase boundaries before execution.
- Plan must be executable one phase at a time.

## Workflow

1. Read the design doc and the minimum code context needed to scope phases.
2. Break work into coarse implementation phases (not tiny task lists).
3. Put 2–4 related tasks in each phase.
4. Assign **one owner per phase by side**:
   - `claude` — simple/trivial tasks Claude handles directly.
   - `codex` — back-side: backend, API, logic, database, system, infra, CI/CD, scripts, server-side tests.
   - `gemini` — front-side: UI, CSS, motion, canvas/SVG, interactions, multimodal, large-context UI/doc sweeps.
   - Full-stack work → split into back-side + front-side sub-phases.
5. Include file set, acceptance criteria, reviewer checklist, integration checks for every phase.
6. Save under `docs/plans/YYYY-MM-DD-<topic>-implementation-plan.md`.
7. Offer execution with `executing-plans`.

## Hard Rules

- Route by side; no default executor.
- No draft-then-reimplement handoffs.
- Cross-Validation only when the phase straddles unresolved architecture spanning both sides.

## Phase Shape

```markdown
### Phase N: [Short outcome]

**Owner:** `claude` | `codex` | `gemini`

**Goal:** [One clear outcome]

**Files:**
- Modify: `path/to/file`
- Create: `path/to/file`

**Tasks:**
1. [related task]
2. [related task]

**Acceptance Criteria:**
- [criterion]

**Reviewer Checklist:**
- [spec requirement]
- [edge case / regression]

**Integration Checks:**
- `exact command`
```

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow, routing, and review.
