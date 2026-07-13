# Implementer Prompt Template

Dispatch template for codex / agy phase workers. The worker contract (per-task workflow, discipline) and response format live in `<project>/.agents/shared/{worker-contract.md,erp.md}` — materialized by the plugin's SessionStart hook and readable by the worker at its `cd`. This file is the per-phase **input** spec only; it points at those two files instead of restating them.

## MCP call

Default: prompt body lives in `<plan-dir>/phase-<NN>/prompt.md`; the MCP `PROMPT` field is a thin pointer. Inline only for one- or two-sentence asks with no context block.

```text
mcp__plugin_superpowers-ccg_openmcp__run:
  backend: "codex" (back-side) | "agy" (front-side)
  cd: <repo root>
  PROMPT: |  
    You are a [role description and expertise areas]...
    
    Scope: [one sentence scope — e.g. "Implement the user authentication API per the spec."]

    Read your full task spec from: docs/plans/<slug>/phase-<NN>/prompt.md
    Plan dir:   docs/plans/<slug>
    Phase dir:  docs/plans/<slug>/phase-<NN>
    Phase:      <N>
    Contract:   .agents/shared/worker-contract.md
    Response:   .agents/shared/erp.md
    Follow the contract and the spec file. Respond per erp.md, then emit the completion line.

    Output: Respond per the ERP contract.
```

Set `cd` to the repo root; every path in the prompt body is relative to it.

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

Follow `.agents/shared/worker-contract.md` for the per-task workflow and discipline — write `notes.md` / `journal.md` under the Phase dir above.

## Response Format

Respond per `.agents/shared/erp.md` — return the `# EXTERNAL RESPONSE`
block, then the single completion line.

## Same-phase fix

Reuse the cached `SESSION_ID`. Send `FIX:` + only the delta files / delta context. The fix still gets its own task commit and (if it changes a decision) an appended `notes.md` block.