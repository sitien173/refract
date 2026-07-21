---
name: writing-plans
description: "Turns a confirmed design into a resumable phase-based implementation plan with file scope, acceptance criteria, review checks, and verification commands."
---

# Writing Plans

Load `coordinating-multi-model-work` first. This skill defines plan structure;
it does not initialize OpenMCP, resolve current guidance, or execute jobs.

## Workflow

1. Search `docs/plans/*/.handover.md`. If an `ACTIVE` or `BLOCKED` handover
   overlaps the request, resume it with `executing-plans` or surface the block.
2. Read the confirmed design and only enough code to scope the work.
3. Divide work into outcome-based phases with two to four related tasks each.
4. Give each phase a complete task-guidance input describing its intended
   repository change and any distinct consultation or review concerns.
5. Defer workflow and profile resolution until execution unless the user
   explicitly pins an available profile.
6. Specify exact files, acceptance criteria, reviewer checks, fresh integration
   commands, and one Conventional Commit message per phase.
7. Offer execution through `executing-plans`.

## Storage

Every executable plan uses:

```text
docs/plans/<slug>/
  PLAN.md
  .handover.md
```

Create no phase directories yet; Coordinator creates them at phase start.
Initialize `.handover.md` with the canonical schema from
`coordinating-multi-model-work`: `status: ACTIVE`, `current_phase: 0`,
`next_action: "Execute Phase 1"`, null project and phase fields, null profiles,
phase-zero job references, and empty completion lists.

A documentation-only plan may use `docs/plans/<slug>-plan.md` without handover.
Never execute a flat plan; convert it to folder layout first.

## Phase Shape

```markdown
### Phase N: <outcome>

**Task Guide Input:** <complete phase request and distinct use cases>

**Profile:** `<user-pinned profile>` | `Resolve at execution`

**Goal:** <one outcome>

**Files:**
- Modify: `path/to/file`
- Create: `path/to/file`

**Tasks:**
1. <related task>
2. <related task>

**Acceptance Criteria:**
- <observable criterion>

**Reviewer Checklist:**
- <spec or risk to inspect>

**Integration Checks:**
- `<exact command>`

**Commit:** `type(scope): concise outcome`
```

## Rules

- The resume check is mandatory; never replace matching active work.
- Do not call `task_guide` during plan authoring.
- Do not hard-code a default profile, target, model, or provider.
- Do not create `.gitkeep` files or empty phase directories.
- Do not register a project or submit jobs while writing the plan.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — canonical gates and handover schema.
- `skills/executing-plans/SKILL.md` — phase execution and resume.
