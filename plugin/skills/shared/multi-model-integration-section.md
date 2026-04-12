# Multi-Model Integration (Shared Reference)

All skills that invoke external models must follow this pattern.

**Related skill:** `superpowers-ccg:coordinating-multi-model-work`

## Integration Steps

1. Analyze the phase domain using `coordinating-multi-model-work/routing-decision.md`.
2. Reduce scope to one phase with 2-4 related tasks, a clear file set, reviewer checklist, and integration checks.
3. Build a phase-scoped context bundle with refs plus hydrated snippets for that phase.
4. Invoke exactly one primary worker for implementation:
   - Default implementation → `mcp__codex__codex`
   - UI-heavy visual implementation → `mcp__gemini__gemini`
5. Reuse the same worker `SESSION_ID` for follow-up fixes on that phase only, and send deltas only.
6. Use `CROSS_VALIDATION` only for architectural uncertainty or true multi-domain conflicts.
7. Run Claude review on the resulting artifact and return `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
8. Run integration checks after every phase.

## Invocation

- Use English prompts.
- Send `CONTEXT_REFS` plus `HYDRATED_CONTEXT`, not the full discovery blob.
- Keep `HYDRATED_CONTEXT` under 800 tokens, preferably under 300 tokens.
- Keep executor prompt context under 2500 tokens when practical.
- Same-phase follow-up prompts must send deltas only and stay under 1000 tokens when practical.
- Ask for `# EXTERNAL RESPONSE PROTOCOL v1.1` with complete final file content preferred and unified diff as fallback.
- Do not ask the worker for draft code that the orchestrator will re-implement.

## Checkpoint Integration

- CP1: route the current phase
- CP2: execute the phase externally and receive final file content or unified diff
- CP3: reconcile multiple or non-trivial external responses before final review
- CP4: perform Claude phase review

## Fallback

If `Routing == Gemini` and Gemini fails once with `timeout`, `tool-unavailable`, or session/tool instability, fall back to Codex or Claude-code. Do not retry Gemini multiple times.

If `Routing == Codex` and Codex fails with `timeout` or `tool-unavailable`, retry once with identical parameters. If still failing, fall back to a Sonnet subagent (`Agent` tool, `model: "sonnet"`) that implements the phase via direct file editing. Use `coordinating-multi-model-work/prompts/sonnet-fallback-base.md` as the prompt template.

CP4 runs identically after fallback.

If the failure reason is `permission-blocked`, do not retry or fall back — output `BLOCKED` per `coordinating-multi-model-work/GATE.md`.
