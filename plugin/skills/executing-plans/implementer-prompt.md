# Implementer Prompt Template

Use when dispatching Codex or Gemini worker for one phase.

```text
External model call:
  target: mcp__codex__codex (back-side) or mcp__gemini__gemini (front-side)
  description: "Implement Phase N: [phase name]"
  prompt: |
    You own one implementation phase with 2–4 related tasks.

    ## Original User Request
    [one or two compressed sentences]

    ## Phase
    [phase summary — one sentence]

    ## Context
    [small snippets from existing files only — no pre-written implementation]

    ## Files
    [flat list of file paths]

    ## Done When
    - [acceptance criterion]
    - [integration check command]

    ## Rules
    - Edit files directly with your write tools; on-disk files are the source of truth.
    - Do not duplicate file content in the response.
    - Do not redesign the phase or produce a reference prototype.
    - If anything is unclear, list it under CLARIFICATIONS NEEDED.
    - Context excerpts are reference only — never pre-write new file contents in the prompt.
    - Keep the response compact.

    ## Report Format
    # EXTERNAL RESPONSE

    ## SUMMARY
    [one sentence]

    ## FILES MODIFIED
    | Action  | Path     | Change |
    |---------|----------|--------|
    | Created | src/...  | ...    |
    | Edited  | src/...  | ...    |

    ## SPEC COMPLIANCE
    - Meets Spec? YES | WITH_DEBT | NO
    - Explanation: [one line]

    ## CLARIFICATIONS NEEDED
    None (or list questions)

    ## NEXT
    TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE
```

## Prompt discipline

- Keep prompt compact. Long input (>~8KB / >1500 tokens) → write to repo file (prefer `docs/plans/`), pass path.
- Same-phase fix: reuse `SESSION_ID`, send `FIX:` + delta files + delta context only.
- One phase, one owner. Never send whole plan to worker.