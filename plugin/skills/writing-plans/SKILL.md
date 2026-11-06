---
name: writing-plans
description: "Use when a confirmed design needs an implementation plan, or the user asks to break agreed work into phases. Produces a resumable phase plan with baseline evidence, exact files, invariants, acceptance criteria, review checks, and verification commands. Without a confirmed design, use brainstorming first."
---

# Writing Plans

## Role

This skill owns plan structure only. Load `coordinating-multi-model-work`
first; it owns routing, execution, anchors, and Git.

## Constraints

- Do not call `list` or `submit` while authoring.
- Do not hard-code a default profile, target, model, or provider. Record a
  profile only when the user pins one.
- Never replace matching active work: a plan for the same topic whose handover
  status is not `DONE`.
- Every path, criterion, and command is exact and checkable. Each command must
  exist today and pass at the plan `base`. When one fails, the first phase
  repairs the baseline; otherwise every later evidence gate proves nothing.

## Workflow

1. **Resume check.** Read `docs/plans/*/.handover.md`. When one matches the
   topic and is not `DONE`, stop and offer `executing-plans`,
   `executing-plans-autonomously`, or a new slug.
2. **Inputs.** Require a confirmed `DESIGN.md`; without one, offer
   `brainstorming` and stop. Require the Coordinator's plan `base` anchor at
   clean HEAD before creating plan artifacts.
3. **Scope & Baseline.** Read `DESIGN.md` and only enough code to name exact files and
   reuse targets. Run the verification commands at `base` and record their baseline results.
4. **Phase.** Divide work into outcome-based phases of two to four related
   tasks that one implementation job can safely own; smaller work is one phase.
5. **Depend.** A missing `Depends on:` line means the phase depends on the previous phase.
   Mark phases independent only when their `Files:` lists are disjoint and
   neither needs an API, schema, or fixture the other creates. Shared files such as
   lockfiles or `CHANGELOG.md` force a dependency. Reject cycles and unknown phase numbers.
6. **Detail.** Fill the plan header and phase template below. Done when each phase
   has exact files, preserved invariants, observable criteria, reviewer checks, and commands.
7. **Commit.** Specify one Conventional Commit message for the completed plan.
8. **Write.** Create `PLAN.md` and `.handover.md`; checkpoint them under `tracked`.
9. **Confirm.** Ask the user to approve the plan before execution, then offer
   `executing-plans` (phase-by-phase) or `executing-plans-autonomously` (full run).

## Storage

Every executable plan uses `docs/plans/<slug>/` holding `PLAN.md`, `DESIGN.md`,
and `.handover.md`. Initialize handover with the canonical schema: `ACTIVE`,
phase zero, null project and job fields, and empty lists. Create phase
directories, never empty, only during execution. A documentation-only plan may
use `docs/plans/<slug>-plan.md`; convert it to folder layout before execution.

## Plan and Phase Template

This sole branch commit replaces local phase checkpoints after every phase passes:

```markdown
# <Topic> Plan

**Design:** [DESIGN.md](DESIGN.md)
**Context key:** `<slug>`
**Base:** `refs/plans/<slug>/base` (`<sha>`)
**Commit:** `type(scope): concise plan outcome`

## Outcome & Scope
<overall goal, preserved invariants, and out-of-scope boundaries>

## Baseline Evidence
- `<exact command>`: <pass/skip counts at plan base>

### Phase N: <outcome>

**Task Guide Input:** <complete phase request and distinct use cases>
**Goal:** <one outcome>
**Depends on:** <Phase N, Phase M | none>
**Invariants & Boundaries:** <what to preserve; what is out of scope>
**Files:**
- Modify: `path/to/file`
- Create: `path/to/file`
**Tasks:**
1. <related TDD task>
**Acceptance Criteria:**
- <observable criterion>
**Reviewer Checklist:**
- <risk or requirement to inspect>
**Verification Checks:**
- `<exact command>`
```
