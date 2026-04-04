# Implementer Prompt Template

Use this template when dispatching a worker for one bounded task.

```text
External model call:
  target: Codex MCP or Gemini MCP (follow the CP1 route)
  description: "Implement Task N: [task name]"
  prompt: |
    You own one bounded implementation task.

    ## Original User Request
    [compressed original user request]

    ## Task Context Bundle
    TASK_ID: [stable bounded-task id]

    ## Context Refs
    - [artifact id]
    - [artifact id]

    ## Hydrated Context
    [only the small context snippets needed to complete this bounded task]

    ## CP1 Task Summary
    [FULL TEXT of the current bounded task only]

    ## Files
    [explicit file set]

    ## Success Criteria
    [acceptance criteria]

    ## Verify
    [exact verify command]

    ## Rules
    - If anything is unclear, record it under CLARIFICATIONS NEEDED.
    - Do not redesign the task.
    - Do not produce a reference prototype.
    - Return complete final file content whenever practical.
    - Use unified diff patch only when full content is impractical.

    ## Report Format
    # EXTERNAL RESPONSE PROTOCOL v1.1

    ## SUMMARY
    [one sentence]

    ## FILES MODIFIED
    | Action  | File Path          | Description of Change |
    |---------|--------------------|-----------------------|
    | Created | src/...            | ...                   |
    | Edited  | src/...            | ...                   |

    ## FILE CONTENTS
    [complete final file content for each modified file, preferred; unified diff patch only when full content is impractical]

    ## CONTEXT ARTIFACTS
    [optional reusable artifacts discovered or updated during execution]

    ## SPEC COMPLIANCE
    - Meets Spec? YES / PARTIAL / NO
    - Explanation: ...

    ## CLARIFICATIONS NEEDED
    None (or list questions)

    ## NEXT STEPS / CONTINUATION
    TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
```
