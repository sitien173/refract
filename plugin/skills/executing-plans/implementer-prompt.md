# Implementer Prompt Template

Dispatch template for Codex / Gemini phase workers. The worker contract (per-task workflow, discipline) and response format live in `<project>/.agents/shared/{worker-contract.md,erp.md}` — materialized by the plugin's SessionStart hook and readable by the worker at its `cd`. This file is the per-phase **input** spec only; it points at those two files instead of restating them.

## MCP call

Default: prompt body lives in `<plan-dir>/phase-<NN>/prompt.md`; the MCP `PROMPT` field is a thin pointer. Inline only for one- or two-sentence asks with no context block.

```text
mcp__openmcp__run:
  backend: "codex" (back-side) | "gemini" (front-side)
  cd: <ABSOLUTE repo root>
  PROMPT: |
    [one sentence of persona / mindset — e.g. "You are an experienced backend engineer implementing the API endpoints for Phase N with clean code and good test coverage."]

    Read your full task spec from: <ABSOLUTE>/docs/plans/<slug>/phase-<NN>/prompt.md
    Plan dir:   <ABSOLUTE>/docs/plans/<slug>
    Phase dir:  <ABSOLUTE>/docs/plans/<slug>/phase-<NN>
    Phase:      <N>
    Contract:   <ABSOLUTE>/.agents/shared/worker-contract.md
    Response:   <ABSOLUTE>/.agents/shared/erp.md
    Follow the contract and the spec file. Respond per erp.md, then emit the completion line.
```

**Absolute paths only.** The pointer path, `cd`, and every path inside the prompt body must be absolute with forward slashes on Windows. Gemini/agy mis-resolves relative paths.

## Prompt file (`<plan-dir>/phase-<NN>/prompt.md`)

```markdown
## Original User Request
[one or two compressed sentences]

## Phase
[phase summary — one sentence]

## Tasks
- task-1: <one line>
- task-2: <one line>
- task-3: <one line>

## Context
[small snippets from existing files only — no pre-written implementation]

## Files
[flat list of file paths]

## Done When
- [acceptance criterion]
- [integration check command — its fresh output is the completion evidence]

## Rules

Follow the contract in `<ABSOLUTE>/.agents/shared/worker-contract.md` — per-task
workflow (test-first → one commit per task `phase-<N>.task-<M>: …` → append a
`## Task <M>` block to `phase-<NN>/notes.md` → append the `# EXTERNAL RESPONSE`
block to `phase-<NN>/journal.md`) plus the discipline rules (test-first,
root-cause-first, evidence) and prompt discipline (edit on disk, no duplication,
no redesign, unclear → CLARIFICATIONS NEEDED + stop). Use the absolute
`notes.md` / `journal.md` paths under the Phase dir above.

## Response Format

Respond per `<ABSOLUTE>/.agents/shared/erp.md` — return the `# EXTERNAL RESPONSE`
block, then the single completion line.

## Same-phase fix

Reuse the cached `SESSION_ID`. Send `FIX:` + only the delta files / delta context. The fix still gets its own task commit and (if it changes a decision) an appended `notes.md` block.