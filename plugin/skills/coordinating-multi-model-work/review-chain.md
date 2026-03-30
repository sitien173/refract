# Review Chain (Canonical Reference)

This is the single source of truth for the review chain rule. All other files reference this document.

## The Rule

```
FinalArbiter = Opus
```

## What This Means

| Implementer | Reviewer |
|-------------|----------|
| Codex | Opus |
| Gemini | Opus |
| Cursor | Opus |
| Docs-only | Skip |

## Key Rules

- **Opus has final say** on every code-changing path
- All implementers (Codex, Gemini, Cursor) are reviewed directly by Opus
- If Opus is unavailable for a code-changing path: **BLOCKED**
- Max **3 fix-review loops** before escalating to user
- Docs-only changes are exempt from quality review

## Cursor Model Policy

- **As implementation agent** (CURSOR routing — DevOps only): `claude-4.6-sonnet-medium-thinking`
- **As cross-validation participant** (optional 3-way): `claude-4.5-opus-high-thinking`

## Review Rules

- Opus reviews implementation directly against the diff and task context
- If Opus finds issues: implementer fixes, re-run Opus
- After substantive fixes: re-run Opus against the new commit

## Artifact Pinning

All CP3 reviews must reference the same commit SHA. If fixes invalidate an earlier review, re-run Opus against the new SHA.
