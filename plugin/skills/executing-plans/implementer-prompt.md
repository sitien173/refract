# Implementer Prompt Template

Dispatch template for Codex / Gemini phase workers. The worker response format (`# EXTERNAL RESPONSE` block, `## COMMITS`, `## NOTES`, completion line) is canonical in `coordinating-multi-model-work` — workers follow that spec; this file is the per-phase **input** spec only.

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
    Follow every rule in the spec file. Emit the completion line when done.
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
- Edit files directly with your write tools; on-disk files are the source of truth.
- Do not duplicate file content in the response.
- Do not redesign the phase or produce a reference prototype.
- **Test-first (TDD):** for any feature/bugfix, write the failing test first and
  watch it fail, then write minimal code to pass. No production code without a
  failing test first.
- **Bug fixes:** find the root cause before fixing; the fix starts from a failing
  test reproducing the bug. Never fix a bug without a test.
- If anything is unclear, list it under CLARIFICATIONS NEEDED and stop.

## Per-Task Workflow
For each task in order:
  1. Implement test-first where it applies: write the failing test, run it, confirm RED; then minimal code to GREEN.
  2. `git add` only files touched for this task; commit with subject `phase-<N>.task-<M>: <one-line>`. Capture the hash.
  3. Append a `## Task <M>` block to `<ABSOLUTE>/docs/plans/<slug>/phase-<NN>/notes.md` (create with heading `# Phase <N> — Decision Notes` if missing). Sub-sections: Decisions made (not in spec), Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human, Test evidence (RED→GREEN, or root cause for a fix). Empty sub-sections = `- none`.
  4. Append the commit row to `## COMMITS` in your response.

## After All Tasks
- Append the full `# EXTERNAL RESPONSE` block (same content you return inline) under the `## External Response` heading of `<ABSOLUTE>/docs/plans/<slug>/phase-<NN>/journal.md`. Do not overwrite earlier sections.

## Response Format

Return the canonical `# EXTERNAL RESPONSE` block defined in `coordinating-multi-model-work` (META, SUMMARY, FILES MODIFIED, COMMITS, NOTES, SPEC COMPLIANCE, CLARIFICATIONS NEEDED, NEXT), then the single completion line. Do not restate the schema here — follow that spec.

## Same-phase fix

Reuse the cached `SESSION_ID`. Send `FIX:` + only the delta files / delta context. The fix still gets its own task commit and (if it changes a decision) an appended `notes.md` block.