# Review Chain (Canonical Reference)

This is the single source of truth for the review chain rule.

## The Rule

```text
FinalArbiter = Opus
```

## What This Means

| Implementer | Reviewer |
|-------------|----------|
| Codex | Opus |
| Gemini | Opus |
| Docs-only | Skip |

## Key Rules

- Opus has final say on every code-changing path.
- All implementers are reviewed directly by Opus.
- If Opus is unavailable for a code-changing path: `BLOCKED`.
- Max 3 fix-review loops before escalating to the user.
- Docs-only changes are exempt from quality review.
