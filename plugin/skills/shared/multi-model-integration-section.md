# Multi-Model Integration (Shared Reference)

All skills that invoke external models MUST follow this integration pattern.

**Related skill:** `superpowers-ccg:coordinating-multi-model-work`

## Integration Steps

1. **Analyze task domain** using `coordinating-multi-model-work/routing-decision.md`
2. **Notify user:** "I will use [model] to [task purpose]"
3. **Invoke model** via MCP tools:
   - Backend → `mcp__codex__codex`
   - Frontend → `mcp__gemini__gemini`
   - Backend and systems (API, DB, scripts, CI/CD, infrastructure) → `mcp__codex__codex`
   - Full-stack/uncertain → Call multiple MCP tools (CROSS_VALIDATION)
4. **Run the review chain** per `coordinating-multi-model-work/review-chain.md`
5. **Integrate results** before proceeding

## Invocation

Use English prompts. See `coordinating-multi-model-work/INTEGRATION.md` for templates.

## Checkpoint Integration

At skill checkpoints, apply routing from `coordinating-multi-model-work/checkpoints.md`:
- CP1: Decide routing, invoke external model if `Routing != CLAUDE`
- CP2: Re-evaluate on stalls, cross-validate on ambiguity
- CP3: Run review chain, record evidence

## Fallback (Fail-Closed)

If `Routing != CLAUDE` and the MCP call fails or times out, **STOP** and follow `coordinating-multi-model-work/GATE.md`. Do not proceed with a final answer.
