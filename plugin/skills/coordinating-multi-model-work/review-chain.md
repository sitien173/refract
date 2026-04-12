# Phase Review (Canonical Reference)

This is the single source of truth for CP4 Phase Review.

## The Rule

```text
PhaseReviewer = Claude
```

## What This Means

| Artifact Type | Reviewer |
|---------------|----------|
| Any completed workflow artifact | Claude in CP4 |

## Key Rules

- CP4 runs after each implementation phase.
- CP4 checks whether the result satisfies the original request, CP1 success criteria, reviewer checklist, and integration expectations.
- CP4 does not perform broad code quality, style, redundancy, or best-practice review unless listed in the phase checklist.
- `PASS` completes the phase.
- `PASS_WITH_DEBT` completes the phase with explicit non-blocking debt.
- `FAIL` requires a retry, follow-up, or user clarification before integration can continue.
