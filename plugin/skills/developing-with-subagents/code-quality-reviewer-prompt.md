# Code Quality Review (Opus)

Use this template when dispatching code review after spec compliance passes.

## Review Selection

**Rule:** `Reviewer = Opus`

| Implementer | Reviewer |
|-------------|----------|
| Codex (`mcp__codex__codex`) | Opus subagent |
| Gemini (`mcp__gemini__gemini`) | Opus subagent |

## Invocation

Dispatch an Opus subagent using `superpowers-ccg:code-reviewer` for every code-changing path.

```text
1. Log: `[Quality Review] Dispatching Opus reviewer`
2. Dispatch Opus subagent using `superpowers-ccg:code-reviewer`
3. Use BASE_SHA/HEAD_SHA and task context
4. Include diff and original task spec
```

## Review Loop

- If Opus returns issues: implementer fixes, then re-submit to Opus
- Standard tasks: max 3 fix-review loops
- Critical tasks: escalate after repeated review loops
- If Opus approves: mark task complete
