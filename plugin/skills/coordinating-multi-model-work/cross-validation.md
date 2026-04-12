# Cross-Validation Mechanism

Cross-validation is for arbitration, not for routine implementation.

## Use It Only When

- the task has unavoidable frontend and backend coupling
- two competing designs remain after scope reduction
- one worker pass did not remove the ambiguity

## Do Not Use It When

- one worker can own the task cleanly
- you only want a prototype or a second opinion
- the implementation can be split into smaller phases

## Pattern

1. Ask Codex and Gemini the same narrow question.
2. Collect concise answers.
3. Compare only the disagreements.
4. Choose a direction.
5. Route implementation to one worker.

## Output

```markdown
## Cross-Validation Summary

**Agreement:** [shared conclusions]

**Divergences:**
| Aspect | Codex | Gemini | Resolution |
|--------|-------|--------|------------|

**Next worker:** [CODEX or GEMINI]
```
