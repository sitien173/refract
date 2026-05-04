# Block Executor Failures Design

## Goal

Remove fallback execution paths from the live CCG workflow. When Codex or Gemini MCP execution fails, the phase stops with `BLOCKED` instead of retrying, switching executors, or dispatching Sonnet/Claude-code fallback work.

## Scope

Change active workflow files only:

- `skills/coordinating-multi-model-work/`
- `skills/shared/multi-model-integration-section.md`
- `skills/executing-plans/SKILL.md`
- `skills/executing-phases/SKILL.md`
- repository-level user-facing docs/hooks that describe live workflow behavior
- tests that assert fallback wording or behavior

Leave historical plan `docs/plans/2026-04-06-sonnet-fallback-strategy-design.md` unchanged.

## Behavior

Any Codex or Gemini MCP execution failure during CP2 blocks the phase immediately:

- `timeout` → `BLOCKED`
- `tool-unavailable` → `BLOCKED`
- `session-failed` / session instability → `BLOCKED`
- `permission-blocked` → `BLOCKED`

There is no Gemini-to-Codex fallback, no Codex retry, no Claude-code fallback, and no Sonnet worker fallback.

## File Changes

Delete:

- `skills/coordinating-multi-model-work/prompts/sonnet-fallback-base.md`

Update live policy wording in:

- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/coordinating-multi-model-work/checkpoints.md`
- `skills/coordinating-multi-model-work/GATE.md`
- `skills/coordinating-multi-model-work/context-sharing.md` if it references Sonnet fallback state
- `skills/coordinating-multi-model-work/prompts/gemini-base.md`
- `skills/shared/multi-model-integration-section.md`
- `skills/executing-plans/SKILL.md`
- `skills/executing-phases/SKILL.md`
- `superpowers-ccg.md`
- `README.md`
- hook prompt text under `hooks/`

Update tests only where they assert fallback language.

## Evidence Format

Remove live `FALLBACK` evidence blocks. Use `BLOCKED` evidence for all MCP execution failures:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Status: BLOCKED
Reason: permission-blocked | tool-unavailable | timeout | session-failed
```

## Verification

Run targeted text search to confirm no live fallback references remain outside the historical plan and unrelated generic words. Run relevant skill tests:

```bash
./tests/claude-code/run-skill-tests.sh --test test-executing-phases.sh
```

If broader wording changed, also run:

```bash
./tests/claude-code/run-skill-tests.sh
```
