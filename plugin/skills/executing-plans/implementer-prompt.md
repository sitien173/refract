# Implementer Prompt Template

This file owns the goal-oriented meta-prompt (`phase-<NN>/prompt.md`) and the Gate 2 `submit.prompt` envelope. The Coordinator synthesizes `PLAN.md`, `DESIGN.md`, `.handover.md`, and current code into a self-contained specification so the external worker has zero ambiguity about the desired end-state, architectural invariants, and scope boundaries.

Write `<plugin-root>` and `<repo-root>` as absolute paths. Workers run without the plugin loaded and can mis-resolve relative paths.

## Meta-Prompting Principles

- **Goal & Outcome First:** State the exact behavioral end-state and why it matters to the plan before listing tasks.
- **Explicit Invariants:** Name architectural rules, contracts, and existing behaviors that must remain unchanged.
- **Strict File Partition:** Separate editable code/test paths, worker-owned phase records (`notes.md`, `journal.md`), and read-only/forbidden paths.
- **Verifiable Completion:** Pair every acceptance criterion with exact commands runnable from `<repo-root>` and baseline expectations.

## Phase Prompt (`docs/plans/<slug>/phase-<NN>/prompt.md`)

```markdown
# Phase <N>: <phase title>

## Goal & Outcome
- Plan Goal: <concise statement of overall plan objective>
- Phase Outcome: <exact capability or state change this phase delivers>

## Context & Architecture
- Root: `<repo-root>` | Branch: `<branch>` | Base: `refs/plans/<slug>/phase-<NN>/base`
- Prior State: <summary of completed phases or baseline state>
- Code Context: <existing modules, symbols, data flow, and reuse targets>

## Invariants & Boundaries
- Preserve: <existing behaviors, schemas, or APIs that must not break>
- Out of Scope: <later phases, unrelated subsystems, or forbidden operations>

## Files
Allowed production and test paths:
- `<path/to/file>` (<create | modify: exact responsibility>)

Worker-owned phase records:
- `docs/plans/<slug>/phase-<NN>/notes.md` (append `## Task <M>` blocks)
- `docs/plans/<slug>/phase-<NN>/journal.md` (append `# EXTERNAL RESPONSE` under `## Implementation Response`)

Read-only / Forbidden:
- Do not edit `PLAN.md`, `DESIGN.md`, `.handover.md`, `prompt.md`, other phases, dependencies, or secrets.

## Tasks
- task-1: <TDD step: failing test/reproduction -> minimal implementation -> verification>
- task-2: <next ordered step>

## Done When
- <observable acceptance criterion>
- Run from `<repo-root>`:
  - `<exact verification command>` (Baseline: <expected baseline result>)

## Rules
Read and follow these bundled contracts:
- Contract: `<plugin-root>/shared/worker-contract.md`
- Response: `<plugin-root>/shared/erp.md`
- Notes: `<plugin-root>/shared/notes-template.md`
- Journal: `<plugin-root>/shared/journal-template.md`

Role boundary: You are the phase implementer, not Coordinator. Work directly in `<repo-root>`. Do not run Git commits, resets, stashes, branch changes, or ref updates. Do not invoke Coordinator skills or submit nested jobs. Use `refract ask "<question>"` for unresolved spec questions, or return `NEXT: BLOCKED` if unavailable.

## Response Format
Append the complete `# EXTERNAL RESPONSE` block to `docs/plans/<slug>/phase-<NN>/journal.md`, then return that block and the matching status line from `erp.md`.
```

## Gate 2 Dispatch Envelope (`submit.prompt`)

Pass a self-contained prompt to `submit(path="<repo-root>", workflow="implement", fresh=true, ...)`:

```text
You are the Phase <N> Implementer for plan `<slug>` in `<repo-root>`.
1. Read `<plugin-root>/shared/worker-contract.md` and `<plugin-root>/shared/erp.md`.
2. Read and execute `<repo-root>/docs/plans/<slug>/phase-<NN>/prompt.md` completely.
3. Stay strictly within the declared file set, record RED->GREEN evidence per task in `notes.md`, append `# EXTERNAL RESPONSE` to `journal.md`, and return the ERP block plus status line.
```
