---
name: writing-plans
description: "Turns a confirmed design into a phase-based implementation plan. Each phase has 2–4 tasks, one owner, file set, acceptance criteria, and integration checks."
---

# Writing Plans

Phase-plan author. The routing table, owner semantics, and resume artifacts all live in `coordinating-multi-model-work` — load it first.

## Use When

- Design is confirmed and the user wants an implementation plan.
- Work needs phase boundaries before execution.

## Workflow

1. **Resume check first.** Glob `docs/plans/*/.handover.md` and read each frontmatter. Any `status: ACTIVE` handover whose topic overlaps the user request → STOP and hand off to `executing-plans`. Ask the user if the topic match is unclear.
2. Read the design doc + minimum code context needed to scope phases.
3. Break the work into coarse phases (not tiny task lists); 2–4 related tasks per phase.
4. Assign **one owner per phase by side** per `coordinating-multi-model-work` routing rules. Full-stack phases split into back-side + front-side sub-phases.
5. Each phase specifies: goal, files (modify/create), tasks, acceptance criteria, reviewer checklist, integration checks.
6. **Pick storage layout:**
   - Multi-phase / multi-session → folder `docs/plans/<slug>/` containing only `PLAN.md` + a `.handover.md` skeleton per the canonical schema (`status: ACTIVE`, `current_phase: 0`, `next_action: "Execute Phase 1"`, empty `completed_tasks`, null `session_refs`). **No `phase-NN/` directories at write time** — they are created lazily by the coordinator at phase start.
   - Single-phase / docs-only → flat `docs/plans/<slug>-implementation-plan.md` (no resume artifacts).
7. Offer execution via `executing-plans`.

## Hard Rules

(Routing, CV triggers, and phase-ID padding are canonical in `coordinating-multi-model-work`. Plan-author specifics:)

- Resume check is mandatory — never start fresh when an `ACTIVE` handover covers the topic.
- Folder-layout plans scaffold only `PLAN.md` + `.handover.md`. No `.gitkeep`, no empty dirs.

## Phase Shape

```markdown
### Phase N: [Short outcome]

**Owner:** `coordinator` | `codex` | `agy`

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

**Integration Checks:**
- `exact command`
```

## References

- `skills/coordinating-multi-model-work/SKILL.md` — canonical 3-gate workflow, routing table, resume-artifact schema.
- `skills/executing-plans/SKILL.md` — runs the plan one phase at a time.
