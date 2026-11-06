# Phase 1: Plans declare dependencies and handover records wave state

## Goal & Outcome
- Plan Goal: Plans may declare phase dependencies. Phases with no unmet dependency form a wave; a multi-phase wave implements each phase concurrently in its own worktree, then integrates and reviews each phase serially on the main checkout in plan order.
- Phase Outcome: The `writing-plans` plan template and the handover schema can express phase dependencies and wave state. No execution behavior is described in this phase.

## Context & Architecture
- Root: `/home/ngosi/projects/refract` | Branch: `main` | Base: `refs/plans/parallel-phase-waves/phase-01/base`
- Prior State: Baseline only. `plugin/tests/run.sh` exits 0 at base.
- Read first: `/home/ngosi/projects/refract/docs/plans/parallel-phase-waves/DESIGN.md` (sections "Plan format, owned by `writing-plans`" and "Handover schema additions") and `/home/ngosi/projects/refract/docs/plans/parallel-phase-waves/PLAN.md` ("Outcome & Scope" refinement paragraph and "Phase 1").
- Code Context:
  - `plugin/skills/writing-plans/SKILL.md` owns the phase template; each phase has `**Task Guide Input:**`, `**Goal:**`, `**Invariants & Boundaries:**`, `**Files:**`, and so on.
  - `plugin/skills/coordinating-multi-model-work/references/handover.md` owns the `.handover.md` YAML front matter schema, "Initial values", "Field rules", and "Checklist" sections.
  - `plugin/tests/test-contracts.sh` is a bash script with embedded `python3` heredocs asserting document contents. Follow its existing assertion style; run it from `plugin/` via `plugin/tests/run.sh`.
  - `plugin/scripts/refract-stats` parses only top-level front matter keys and single-line flow-mapping list items. That is why wave state uses two top-level keys, not a nested mapping. Do not edit `refract-stats` in this phase.

## Invariants & Boundaries
- Preserve: every existing template field and handover field keeps its name and meaning. `checklist` keeps its flow-mapping list style. All existing `test-contracts.sh` assertions keep passing unchanged. `plugin/skills/using-git-worktrees/SKILL.md` and `coordinating-multi-model-work/SKILL.md` line limits and other size guards keep passing.
- A missing `Depends on:` line means the phase depends on the previous phase. Do not word anything to imply a new default.
- Out of Scope: wave execution mechanics (`waves.md`, Phase 2), execution skills (Phase 3), worker files (Phase 4), `refract-stats` (Phase 5), version bump (Phase 6). Do not mention worktrees, rebase, or fast-forward in these files. Nothing under `server/` changes.

## Files
Allowed production and test paths:
- `plugin/skills/writing-plans/SKILL.md` (modify: template line and dependency authoring rules)
- `plugin/skills/coordinating-multi-model-work/references/handover.md` (modify: `wave_base` and `wave` schema, initial values, field rules, checklist rule)
- `plugin/tests/test-contracts.sh` (modify: new assertions)

Worker-owned phase records:
- `/home/ngosi/projects/refract/docs/plans/parallel-phase-waves/phase-01/notes.md` (append `## Task <M>` blocks)
- `/home/ngosi/projects/refract/docs/plans/parallel-phase-waves/phase-01/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, other plans under `docs/plans/`, dependencies, or secrets.

## Tasks
- task-1: RED then GREEN. In `test-contracts.sh`, assert the `writing-plans` template contains the line `**Depends on:** <Phase N, Phase M | none>` placed after `**Goal:**`, and assert these rules exist: a missing line means the phase depends on the previous phase; phases may be independent only when their `Files:` lists are disjoint and neither needs an API, schema, or fixture the other creates; shared files such as lockfiles or `CHANGELOG.md` force a dependency; the author rejects cycles and unknown phase numbers. Run to see RED, then edit `writing-plans/SKILL.md` to GREEN.
- task-2: RED then GREEN. Assert and add to the `handover.md` schema block `wave_base: <commit|null>` and `wave: [{ phase, state: implementing|implemented|integrating|integrated|requeued, worktree, branch, implementation_job }, ...]`. Add initial values `wave_base: null` and `wave: []`. Add field rules: a missing key reads as `null` or `[]`; outside a multi-phase wave they stay `null` and `[]`; `implementation_job` is set immediately after `submit` returns, before waiting; `current_phase` and `job_refs` describe the phase running gates on the main checkout.
- task-3: RED then GREEN. Assert and change the checklist rule "Keep at most one step `doing`" to at most one `doing` step per phase.

## Done When
- `writing-plans/SKILL.md` template contains `**Depends on:**` and every rule in task-1.
- `handover.md` schema contains `wave_base:` and `wave:` with all five states and the rules in task-2 and task-3.
- New `test-contracts.sh` assertions fail before the doc edits and pass after.
- Run from `/home/ngosi/projects/refract`:
  - `plugin/tests/run.sh` (Baseline: exit 0, "contract tests passed", "stats tests passed", 3 pre-existing `agy` warnings)
  - `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src` (Baseline: exit 0)

## Rules
Read and follow these bundled contracts:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `/home/ngosi/projects/refract`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `/home/ngosi/projects/refract/docs/plans/parallel-phase-waves/phase-01/journal.md`, then return that block and the matching status line from `erp.md`.
