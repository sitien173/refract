# Implementer Prompt Template

Dispatch template for codex and agy phase workers. The worker contract, response
format, and templates live under the installed plugin's absolute `shared/` path.
This file is the per-phase input specification.

## MCP call

Default: prompt body lives in `<plan-dir>/phase-<NN>/prompt.md`; the MCP `PROMPT` field is a thin pointer. Inline only for one- or two-sentence asks with no context block.

```text
mcp__plugin_superpowers-ccg_openmcp__run:
  backend: "codex" (backend) | "agy" (frontend)
  cd: <repo root>
  timeout_s: 900
  PROMPT: |  
    You are a [role description and expertise areas]...
    
    Scope: [one sentence scope — e.g. "Implement the user authentication API per the spec."]

    Read your full task spec from: docs/plans/<slug>/phase-<NN>/prompt.md
    Plan dir:   docs/plans/<slug>
    Phase dir:  docs/plans/<slug>/phase-<NN>
    Phase:      <N>
    Contract:   <plugin-root>/shared/worker-contract.md
    Response:   <plugin-root>/shared/erp.md
    Notes:      <plugin-root>/shared/notes-template.md
    Journal:    <plugin-root>/shared/journal-template.md
    Follow the contract and the spec file. Respond per erp.md, then emit the completion line.

    Output: Respond per the ERP contract.
```

Set `cd` to the repo root. Repository paths are relative to it. Bundled contract
paths are absolute. Workers must never stage, commit, reset, or squash.

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

Follow the absolute bundled worker-contract path for execution discipline. Write
`notes.md` and `journal.md` under the Phase directory above.

## Response Format

Respond per the absolute bundled ERP path. Return the `# EXTERNAL RESPONSE`
block, then its matching status line.

## Same-phase fix

Reuse the cached `SESSION_ID` only for this phase. Send `FIX:` plus only delta
files and context. Append a notes block when decisions change. Do not commit.
