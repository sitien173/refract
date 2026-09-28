---
name: writing-plans
description: "Use when a confirmed design needs an implementation plan - produces a resumable phase plan with explicit scope, acceptance criteria, review checks, and verification commands."
---

# Writing Plans

## Role

This skill owns plan structure only. Load `coordinating-multi-model-work`
first; it owns routing, execution, anchors, and Git.

## Constraints

- Do not call `task_guide`, register a project, or submit jobs while authoring.
- Do not hard-code a default profile, target, model, or provider. Record a
  profile only when the user pins one.
- Never replace matching active work: a plan for the same topic whose handover
  status is not `DONE`.
- Every path, criterion, and command is exact and checkable. Each command must
  exist in this repository today.

## Workflow

1. **Resume check.** Read `docs/plans/*/.handover.md`. When one matches the
   topic and is not `DONE`, stop and offer `executing-plans` or a new slug.
2. **Inputs.** Require a confirmed `DESIGN.md`; without one, offer
   `brainstorming` and stop. Require the Coordinator's plan `base` anchor at
   clean HEAD before creating plan artifacts.
3. **Scope.** Read the confirmed design and only enough code to name exact
   files.
4. **Phase.** Divide work into outcome-based phases of two to four related
   tasks. One phase is what one implementation job can safely own. Work too
   small for two tasks is a single phase.
5. **Detail.** Fill the phase template for every phase. Done when each phase
   has exact files, observable criteria, reviewer checks, and commands.
6. **Commit.** Specify one Conventional Commit message for the completed plan.
7. **Write.** Create `PLAN.md` and `.handover.md`. Under `tracked`, checkpoint
   the plan artifacts.
8. **Confirm.** Ask the user to approve the phase list before any detailing.

## Recommended Next Step

After plan authoring, suggest a separate phase-detailing step:

1. Submit one job through the `consult` workflow.
2. Base it on the confirmed design and completed implementation plan.
3. Ask it for implementation detail on every phase without changing scope.
4. Materialize each result in `phase-<NN>/prompt.md`, `notes.md`, and `journal.md`.
   Write the detail to `prompt.md`; scaffold the others from bundled templates.
   Then offer `executing-plans`.

## Storage

Every executable plan uses `docs/plans/<slug>/` holding `PLAN.md`, `DESIGN.md`,
and `.handover.md`. Initialize handover with the canonical schema: `ACTIVE`,
phase zero, null project and job fields, and empty lists. Create phase
directories, never empty, only during phase detailing or execution.
A documentation-only plan may use `docs/plans/<slug>-plan.md`. Convert a flat
implementation plan to folder layout before execution.

## Plan Commit

Record one plan-level message before the phase sections:
```markdown
**Commit:** `type(scope): concise plan outcome`
```
This sole branch commit replaces local phase checkpoints after every phase passes.

## Phase Template

```markdown
### Phase N: <outcome>

**Task Guide Input:** <complete phase request and distinct use cases>
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
```
