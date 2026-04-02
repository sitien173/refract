# Final Spec Review (Canonical Reference)

This is the single source of truth for CP4 Final Spec Review.

## The Rule

```text
FinalSpecReviewer = Claude
```

## What This Means

| Artifact Type | Reviewer |
|---------------|----------|
| Any completed workflow artifact | Claude in CP4 |

## Key Rules

- CP4 always runs as the final workflow step.
- CP4 checks only whether the result satisfies the original request and CP1 success criteria.
- CP4 does not perform code quality, style, redundancy, or best-practice review.
- `PASS` completes the task.
- `PARTIAL` or `FAIL` require a retry, follow-up, or user clarification.
