# Multi-Model Integration (Shared Reference)

> Tier rules, budgets, `SESSION_POLICY` decisions, and the Tier 3 freshness check are canonical in `skills/coordinating-multi-model-work/context-sharing.md`. This file restates only what consuming skills need.

All skills that invoke external models must follow this pattern.

**Related skill:** `superpowers-ccg:coordinating-multi-model-work`

## Integration Steps

1. Analyze the phase domain using `coordinating-multi-model-work/routing-decision.md`.
2. Reduce scope to one phase with 2-4 related tasks, a clear file set, reviewer checklist, and integration checks.
3. Choose the right prompt tier for the phase and send only the hydrated snippets needed for that tier.
4. Invoke exactly one primary worker for implementation:
   - Default implementation → `mcp__codex__codex`
   - UI-heavy visual implementation → `mcp__gemini__gemini`
5. Reuse the same worker `SESSION_ID` for Tier 2 follow-up fixes on that phase, or Tier 3 cross-phase continuation when CP1 sets `SESSION_POLICY: CONTINUE`.
6. Use `CROSS_VALIDATION` only for architectural uncertainty or true multi-domain conflicts.
7. Run Claude review on the resulting artifact and return `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
8. Run integration checks after every phase.

## Invocation

- Use English prompts.
- Use the 3-tier prompt system for CP2 instead of one monolithic bundle.
- Keep `HYDRATED_CONTEXT` under 300 tokens hard cap.
- Tier 1 initial call should stay under 1500 tokens when practical.
- Tier 2 same-phase follow-up should stay under 400 tokens and send deltas only.
- Tier 3 cross-phase continuation should stay under 600 tokens and include `SESSION_POLICY: CONTINUE`.
- Workers edit files directly via MCP write tools and respond using `# EXTERNAL RESPONSE PROTOCOL v1.1`; responses list `## FILES MODIFIED` without duplicating file content.
- Do not ask the worker for draft code that the orchestrator will re-implement.

## Checkpoint Integration

- CP1: route the current phase and choose `SESSION_POLICY`
- CP2: worker executes the phase externally, edits files directly via MCP, and responds with the changed-file list (no duplicated content)
- CP3: reconcile multiple or non-trivial external responses before final review
- CP4: perform Claude phase review

## Failure Handling

If any Codex or Gemini MCP call fails with `timeout`, `tool-unavailable`, `session-failed`, session instability, model error, or `permission-blocked`, output `BLOCKED` per `coordinating-multi-model-work/GATE.md`.

Do not retry or switch executors after executor MCP failure.

CP4 runs only when executor output exists.
