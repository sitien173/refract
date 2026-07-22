---
name: writing-plans
description: "Turns a confirmed design into a resumable phase plan with explicit scope, acceptance criteria, review checks, and verification commands."
---

# Writing Plans

Load `coordinating-multi-model-work` first. This skill owns plan structure only;
it does not route or execute OpenMCP jobs.

## Workflow

1. Search `docs/plans/*/.handover.md`. Resume or surface any overlapping
   `ACTIVE` or `BLOCKED` plan.
2. Read the confirmed design and only enough code to scope implementation.
3. Divide work into outcome-based phases of two to four related tasks.
4. Give each phase a complete task-guidance input.
5. Specify exact files, acceptance criteria, reviewer checks, fresh verification
   commands, and one Conventional Commit message.
6. Defer workflow and profile resolution until execution unless the user pins an
   available profile.
7. Offer `executing-plans`.

## Storage

Every executable plan uses:

```text
docs/plans/<slug>/
  PLAN.md
  .handover.md
```

Initialize handover with the canonical schema: active status, phase zero, null
project and job fields, and empty completion lists. Do not create phase
directories until execution.

A documentation-only plan may use `docs/plans/<slug>-plan.md`. Convert a flat
implementation plan to folder layout before execution.

## Phase Template

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
- <risk or requirement to inspect>

**Verification Checks:**
- `<exact command>`

**Commit:** `type(scope): concise outcome`
```

## Rules

- Never replace matching active work.
- Do not call `task_guide`, register a project, or submit jobs while authoring.
- Do not hard-code a default profile, target, model, or provider.
- Do not create empty directories or `.gitkeep` files.
