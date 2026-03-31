# Implementer Prompt Template

Use this template when dispatching a worker for one bounded task.

```text
Task tool:
  model: sonnet
  description: "Implement Task N: [task name]"
  prompt: |
    You own one bounded implementation task.

    ## Task
    [FULL TEXT of the current bounded task only]

    ## Files
    [explicit file set]

    ## Acceptance
    [acceptance criteria]

    ## Verify
    [exact verify command]

    ## Rules
    - If anything is unclear, stop and ask questions before coding.
    - Do not redesign the task.
    - Do not produce a reference prototype.
    - Return either:
      1. changed hunks and verification notes
      2. blocking questions

    ## Report Format
    ## DIFF
    [changed hunks only]

    ## VERIFY
    [what you ran / what remains]

    ## ISSUES
    [blocking questions or residual risks]
```
