---
name: writing-plans
description: "Turns a confirmed design into a phase-based implementation plan. Each phase has 2–4 tasks, one owner, file set, acceptance criteria, and integration checks."
---

# Writing Plans

## Use When

- Design confirmed, user wants implementation plan.
- Work needs phase boundaries before execution.
- Plan must be executable one phase at a time.

## Workflow

1. **Resume check first.** Glob `docs/plans/*/.handover.md`. Read frontmatter `plan` + `status`. Any `status: ACTIVE` handover matching user topic (slug overlap or explicit reference) → STOP, hand off to `executing-plans`. If unsure topic matches, ask user.
2. Read design doc + minimum code context to scope phases.
3. Break work into coarse implementation phases (not tiny task lists).
4. Put 2–4 related tasks per phase.
5. Assign **one owner per phase by side**:
   - `claude` — simple/trivial tasks Claude handles directly.
   - `codex` — back-side: backend, API, logic, database, system, infra, CI/CD, scripts, server-side tests.
   - `gemini` — front-side: UI, CSS, motion, canvas/SVG, interactions, multimodal, large-context UI/doc sweeps.
   - Full-stack work → split into back-side + front-side sub-phases.
6. Include file set, acceptance criteria, reviewer checklist, integration checks per phase.
7. **Pick storage layout:**
   - Multi-phase / multi-session → folder `docs/plans/YYYY-MM-DD-<slug>/` containing:
     - `PLAN.md`
     - `.handover.md` skeleton (status `ACTIVE`, current_phase `0`, next_action "Execute Phase 1", `completed_tasks:` empty)
     - `.sessions.json` skeleton (`{ "schema_version": 1, "plan_path": "...", "sessions": { "codex": null, "gemini": null } }`)
     - empty dirs `prompts/`, `notes/`, `responses/` (with `.gitkeep`) — dispatch prompts (per phase), decision notes (per task), EXTERNAL RESPONSE files (per phase)
   - Single-phase / docs-only → flat file `docs/plans/YYYY-MM-DD-<slug>-implementation-plan.md` (no resume artifacts).
8. Offer execution with `executing-plans`.

## Hard Rules

- Route by side; no default executor.
- No draft-then-reimplement handoffs.
- Cross-Validation only when phase straddles unresolved architecture spanning both sides.
- Resume check mandatory before any new plan write. Never start fresh when ACTIVE handover covers topic.
- Folder-layout plans scaffold all resume artifacts at write time: `.handover.md`, `.sessions.json`, and `prompts/`, `notes/`, `responses/` dirs (with `.gitkeep`).

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

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow, routing, review.