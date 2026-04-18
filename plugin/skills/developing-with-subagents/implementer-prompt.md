# Implementer Prompt Template

Use this template when dispatching a worker for one implementation phase.

```text
External model call:
  target: Codex MCP or Gemini MCP (follow the CP1 route)
  description: "Implement Phase N: [phase name]"
  prompt: |
    You own one implementation phase with 2-4 related tasks.

    ## Original User Request
    [compressed original user request]

    ## Phase Context Bundle
    TASK_ID: [stable bounded-task id]

    ## Context Refs
    - [artifact id]
    - [artifact id]

    ## Hydrated Context
    [only the small context snippets needed to complete this phase]

    ## CP1 Phase Summary
    [FULL TEXT of the current phase only]

    ## Files
    [explicit file set]

    ## Success Criteria
    [acceptance criteria]

    ## Reviewer Checklist
    [phase reviewer checklist]

    ## Integration Checks
    [exact commands or repo-state checks]

    ## Prompt Discipline
    - `Hydrated Context` = excerpts from existing files only. Never pre-write new file contents here.
    - For scaffold or greenfield tasks: set Hydrated Context to existing directory structure only, or omit it.
    - Keep Hydrated Context under 800 tokens, preferably under 300 tokens. Over that means over-specifying.
    - Keep the total executor prompt context under 2500 tokens when practical.
    - Same-phase follow-up prompts must send deltas only and stay under 1000 tokens when practical.
    - `Files` = flat list of paths only, not file contents.
    - Pre-writing implementation in the prompt defeats the purpose of routing. Let the worker implement.

    ## Rules
    - If anything is unclear, record it under CLARIFICATIONS NEEDED.
    - Do not redesign the phase.
    - Do not produce a reference prototype.
    - Edit files directly with your write tools. The on-disk files are the source of truth — do not duplicate file content in the response.

    ## Report Format
    # EXTERNAL RESPONSE PROTOCOL v1.1

    ## SUMMARY
    [one sentence]

    ## FILES MODIFIED
    | Action  | File Path          | Description of Change |
    |---------|--------------------|-----------------------|
    | Created | src/...            | ...                   |
    | Edited  | src/...            | ...                   |

    ## CONTEXT ARTIFACTS
    [optional reusable artifacts discovered or updated during execution]

    ## SPEC COMPLIANCE
    - Meets Spec? YES / WITH_DEBT / NO
    - Explanation: ...

    ## CLARIFICATIONS NEEDED
    None (or list questions)

    ## NEXT STEPS / CONTINUATION
    TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
```
