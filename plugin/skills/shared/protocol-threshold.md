# Protocol Threshold (Shared Reference)

All skills that use checkpoints must follow the CP protocol injected by hooks.

## Required Behavior

- Before the first Task call, output a standalone `[CP1 Assessment]` block.
- Before claiming completion or verification, output a standalone `[CP3 Assessment]` block.
- Keep both blocks minimal. The checkpoint is a gate, not a summary.

## CP1 Assessment Format

```text
[CP1 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Complexity: [Trivial/Standard/Critical]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: [one sentence]
```

Compact trivial form:

```text
[CP1] Routing: CLAUDE | Trivial: <reason>
```

## CP3 Assessment Format

```text
[CP3 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: [one sentence]
```

Compact trivial form:

```text
[CP3] Verified: <evidence>
```

## Checkpoint Logic

- **CP1:** decide routing and invoke the worker if needed
- **CP2:** trigger only on real uncertainty, stalled progress, or repeated failures
- **CP3:** verify the artifact and run the review chain
