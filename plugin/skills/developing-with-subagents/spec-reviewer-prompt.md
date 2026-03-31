# Spec Compliance Reviewer Prompt Template

Use this template when dispatching the spec reviewer.

```text
Task tool:
  description: "Review spec compliance for Task N"
  prompt: |
    Verify whether the artifact matches the bounded task.

    ## Requested
    [FULL TEXT of bounded task requirements]

    ## Artifact
    [diff / files changed / commit SHA]

    ## Rules
    - Read the code, do not trust any summary.
    - Check for missing scope, extra scope, or wrong interpretation.
    - Keep the output concise.

    ## Output
    - ✅ Spec compliant
    - ❌ Issues found: [specific missing/extra items with file:line]
```
