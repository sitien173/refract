---
name: writing-plans
description: "Turns a confirmed design into a phase-based implementation plan with route intent, file scope, acceptance criteria, and integration checks. Use when a design is ready and work needs phase boundaries before execution."
---

# Writing Plans

Phase-plan author. The routing contract, owner semantics, and resume artifacts
live in `coordinating-multi-model-work` — load it first.

## Use When

- Design is confirmed and the user wants an implementation plan.
- Work needs phase boundaries before execution.

## Workflow

1. **Resume check first.** Glob `docs/plans/*/.handover.md` and read each frontmatter. Any `ACTIVE` or `BLOCKED` handover whose topic overlaps the request stops fresh planning. Hand active work to `executing-plans`; surface blocked work to the user. Ask when topic matching is unclear.
2. Read the design doc + minimum code context needed to scope phases.
3. Break the work into coarse phases (not tiny task lists); 2–4 related tasks per phase.
4. Describe the phase request and its distinct use cases as route intent. Do not
   infer an agent nickname from task words.
5. Preserve an owner or routing profile only when the user explicitly pins it.
   Otherwise set each value to `Resolve at execution`.
6. Each phase specifies: goal, route intent, owner resolution, profile
   resolution, files, tasks, acceptance criteria, reviewer checklist,
   integration checks, and commit message.
7. **Pick storage layout:**
   - Every executable plan → folder `docs/plans/<slug>/` containing only `PLAN.md` + a `.handover.md` skeleton per the canonical schema (`status: ACTIVE`, `current_phase: 0`, `next_action: "Execute Phase 1"`, empty completion lists, null `routing_profile`, null `phase_base`, null `project_id`, empty `context_prefix`, and phase-zero `job_refs`). **No `phase-NN/` directories at write time** — they are created lazily by Coordinator at phase start.
   - Documentation-only plans that will not execute → flat `docs/plans/<slug>-plan.md` without resume artifacts.
8. Offer execution via `executing-plans`.

## Hard Rules

(Routing, consultation triggers, and phase-ID padding are canonical in `coordinating-multi-model-work`. Plan-author specifics:)

- Resume check is mandatory — never replace matching `ACTIVE` or `BLOCKED` work.
- Folder-layout plans scaffold only `PLAN.md` + `.handover.md`. No `.gitkeep`, no empty dirs.
- Never execute a flat plan. Convert it to folder layout first.
- Do not call `task_route` during plan authoring. The executor resolves current
  project routing when each phase starts.
- Never hard-code default agent nicknames or routing profiles.
- Do not initialize or register OpenMCP while writing plans.

## Phase Shape

```markdown
### Phase N: [Short outcome]

**Route Intent:** [Phase request and distinct use cases]

**Owner:** `<user-pinned nickname>` | `Resolve at execution`

**Routing Profile:** `<user-pinned profile>` | `Resolve at execution`

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

**Commit:** `type(scope): concise outcome`
```

## References

- `skills/coordinating-multi-model-work/SKILL.md` — canonical 3-gate workflow, routing contract, resume-artifact schema.
- `skills/executing-plans/SKILL.md` — runs the plan one phase at a time.
