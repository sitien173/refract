# Protocol Threshold (Shared Reference)

All skills that use checkpoints MUST follow the CP Protocol injected by hooks.

## Required Behavior

- **Before the first Task call:** Output a standalone `[CP1 Assessment]` block (no tool calls in the block itself; tool calls may follow in the same reply)
- **Before claiming completion / requesting review / claiming verification passed:** Output a standalone `[CP3 Assessment]` block (no tool calls in the block itself; the claim may follow in the same reply)

"Standalone" means the CP block must be its own block at the top of the reply. It does NOT mean you should stop after the CP block — continue in the same reply.

If unmet: immediately perform the CP assessment, then continue the flow right away; do not stop or interrupt.

## CP1 Assessment Format

```text
[CP1 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Complexity: [Trivial/Standard/Critical]
- Enforcement mode: [Strict/Degraded/Incident]
- Routing decision: [CLAUDE/CODEX/GEMINI/CURSOR/CROSS_VALIDATION]
- Rationale: ...
```

Compact format (Trivial tasks only):
```text
[CP1] Routing: CLAUDE | Trivial: <reason>
```

## CP3 Assessment Format

```text
[CP3 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Routing decision: [CLAUDE/CODEX/GEMINI/CURSOR/CROSS_VALIDATION]
- Rationale: ...
```

Compact format (Trivial tasks only):
```text
[CP3] Verified: <evidence>
```

## Checkpoint Logic

Apply checkpoint logic from `coordinating-multi-model-work/checkpoints.md` at each stage:

- **CP1 (Task Analysis):** Decide routing, invoke external model if needed
- **CP2 (Mid-Review):** Triggered by uncertainty, stalled debugging, 2+ failed attempts
- **CP3 (Quality Gate):** Run verification, record evidence, run review chain
