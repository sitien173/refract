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

1. **Resume check first.** Glob `docs/plans/*/.handover.md` and read each frontmatter. Any `ACTIVE` or `BLOCKED` handover whose topic overlaps the request stops fresh planning. Hand active work to `executing-plans`; surface blocked work to the user. Ask when topic matching is unclear.
2. Read the design doc + minimum code context needed to scope phases.
3. Break the work into coarse phases (not tiny task lists); 2–4 related tasks per phase.
4. Assign **one owner per phase by side** per `coordinating-multi-model-work` routing rules. Full-stack work splits into backend and frontend phases.
5. Each phase specifies: goal, files (modify/create), tasks, acceptance criteria, reviewer checklist, integration checks.
6. **Pick storage layout:**
   - Every executable plan → folder `docs/plans/<slug>/` containing only `PLAN.md` + a `.handover.md` skeleton per the canonical schema (`status: ACTIVE`, `current_phase: 0`, `next_action: "Execute Phase 1"`, empty completion lists, null `phase_base`, and phase-zero `session_refs`). **No `phase-NN/` directories at write time** — they are created lazily by the coordinator at phase start.
   - Documentation-only plans that will not execute → flat `docs/plans/<slug>-plan.md` without resume artifacts.
7. Offer execution via `executing-plans`.

## Hard Rules

(Routing, CV triggers, and phase-ID padding are canonical in `coordinating-multi-model-work`. Plan-author specifics:)

- Resume check is mandatory — never replace matching `ACTIVE` or `BLOCKED` work.
- Folder-layout plans scaffold only `PLAN.md` + `.handover.md`. No `.gitkeep`, no empty dirs.
- Never execute a flat plan. Convert it to folder layout first.

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
