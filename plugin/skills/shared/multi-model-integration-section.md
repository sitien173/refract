# Multi-Model Integration (Shared Reference)

All skills that invoke external models must follow this pattern.

**Related skill:** `superpowers-ccg:coordinating-multi-model-work`

## Integration Steps

1. Analyze the task domain using `coordinating-multi-model-work/routing-decision.md`.
2. Reduce scope to one bounded task with a clear file set and verification command.
3. Build a task-scoped context bundle with refs plus hydrated snippets for that bounded task.
4. Invoke exactly one worker for implementation:
   - Backend and systems → `mcp__codex__codex`
   - Frontend → `mcp__gemini__gemini`
5. Reuse the same worker `SESSION_ID` for follow-up fixes on that task only, and send deltas only.
6. Use `CROSS_VALIDATION` only for architectural uncertainty or true multi-domain conflicts.
7. Run CP4 Final Spec Review in Claude on the resulting artifact.

## Invocation

- Use English prompts.
- Send `CONTEXT_REFS` plus `HYDRATED_CONTEXT`, not the full discovery blob.
- Ask for `# EXTERNAL RESPONSE PROTOCOL v1.1` with complete final file content preferred and unified diff as fallback.
- Do not ask the worker for draft code that the orchestrator will re-implement.

## Checkpoint Integration

- CP1: route the current bounded task
- CP2: execute the bounded task externally and receive final file content or unified diff
- CP3: reconcile multiple or non-trivial external responses before final review
- CP4: perform the final pure spec review

## Fallback

If `Routing != CLAUDE` and the MCP call fails or times out, stop and follow `coordinating-multi-model-work/GATE.md`.
