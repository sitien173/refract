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

1. **Resume check first.** Glob `docs/plans/*/.handover.md`. For each, read frontmatter `plan` + `status`. If any `status: ACTIVE` handover matches the user's topic (slug overlap or explicit reference), STOP — hand off to `executing-plans` instead of writing a new plan. If unsure whether topic matches, ask the user.
2. Read the design doc and the minimum code context needed to scope phases.
3. Break work into coarse implementation phases (not tiny task lists).
4. Put 2–4 related tasks in each phase.
5. Assign **one owner per phase by side**:
   - `claude` — simple/trivial tasks Claude handles directly.
   - `codex` — back-side: backend, API, logic, database, system, infra, CI/CD, scripts, server-side tests.
   - `gemini` — front-side: UI, CSS, motion, canvas/SVG, interactions, multimodal, large-context UI/doc sweeps.
   - Full-stack work → split into back-side + front-side sub-phases.
6. Include file set, acceptance criteria, reviewer checklist, integration checks for every phase.
7. **Pick storage layout:**
   - Multi-phase / multi-session plan → folder layout `docs/plans/YYYY-MM-DD-<slug>/PLAN.md` + create empty `.handover.md` skeleton (status `ACTIVE`, current_phase `0`, next_action "Execute Phase 1") + `.sessions.json` skeleton (`{ "schema_version": 1, "plan_path": "...", "sessions": { "codex": null, "gemini": null } }`).
   - Single-phase / docs-only plan → flat file `docs/plans/YYYY-MM-DD-<slug>-implementation-plan.md` (no resume artifacts).
8. Offer execution with `executing-plans`.

## Hard Rules

- Route by side; no default executor.
- No draft-then-reimplement handoffs.
- Cross-Validation only when the phase straddles unresolved architecture spanning both sides.
- Resume check is mandatory before any new plan write. Never start fresh when an ACTIVE handover already covers the topic.
- Folder-layout plans MUST create `.handover.md` + `.sessions.json` skeletons at plan-write time so future sessions can resume.

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
