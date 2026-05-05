# Context-Retrieval CP0 Design

## Summary

Replace Auggie with the `context-retrieval` MCP suite for CP0 local code context acquisition. CP0 keeps the same flow: optional `docs/wiki/` durable knowledge lookup, then current local code context, then Grok Search only when external or current-world research is required.

## Goals

- Make `context-retrieval` the only active local CP0 context retrieval contract.
- Use the full context-retrieval suite with clear tool selection rules.
- Keep CP0 context small, normalized, and safe for phase routing.
- Update hooks, rules, docs, skills, and tests together to avoid split-brain instructions.

## Non-Goals

- No Codex/Gemini routing changes.
- No CP1-CP4 block format changes.
- No worker prompt API changes beyond CP0 artifact source.
- No cleanup of historical release notes or old plans unless active tests target them.

## CP0 Tool Contract

CP0 local context uses `context-retrieval` after any useful wiki lookup:

- `mcp__context-retrieval__codebase_retrieve`: default semantic CP0 retrieval for implementation anchors, unfamiliar subsystems, and where/how/what-handles questions.
- `mcp__context-retrieval__codebase_map`: architecture and component relationship mapping for broad refactors, cross-file designs, or unclear file boundaries.
- `mcp__context-retrieval__codebase_grep`: deterministic exact search for known identifiers, stale wording checks, test guard verification, and reference sweeps.

Grok Search remains external/current research only. File tools remain allowed after context-retrieval narrows target files; they are not the primary broad CP0 search mechanism.

## Data Flow

1. User request enters CP0.
2. Claude decides whether `docs/wiki/` lookup is useful.
3. Claude uses context-retrieval for current local code context.
4. Claude normalizes useful findings into small `CONTEXT_ARTIFACTS`: `req/core`, `files/hotspots`, `api/contracts`, `verify/commands`, and `debt/known`.
5. CP1 uses those artifacts to route the next phase.

Raw retrieval output must not be dumped into worker prompts. Only small, budgeted findings may enter `HYDRATED_CONTEXT`.

## Files to Update

- `hooks/session-start.sh`
- `hooks/user-prompt-submit.sh`
- `README.md`
- `superpowers-ccg.md`
- `CLAUDE.md`
- `rules/*.mdc`
- `skills/shared/protocol-threshold.md`
- `skills/shared/supplementary-tools.md`
- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/coordinating-multi-model-work/checkpoints.md`
- `skills/coordinating-multi-model-work/context-sharing.md`
- `tests/claude-code/test-cp0-context-acquisition-guards.sh`
- `tests/claude-code/README.md`

## Tests and Guardrails

Update CP0 tests so active docs must mention context-retrieval and must not mention Auggie. The CP0 guard should require:

- CP0 is still documented before CP1.
- context-retrieval + Grok Search CP0 ordering exists.
- tool matrix includes `codebase_retrieve`, `codebase_map`, and `codebase_grep` roles.
- Grok Search remains external/current-only.
- Architecture diagram still includes CP0 before CP1.

Run the fast skill suite after implementation.

## Risks

- Installed plugin hook text can lag until version bump and plugin reload/update.
- Environments without the context-retrieval MCP will fail CP0 expectations. This is acceptable because the selected design removes Auggie fallback completely.
- Partial edits can produce conflicting runtime instructions, so hooks, docs, and tests must land together.

## Acceptance Criteria

- Active CP0 instructions mention the context-retrieval suite, not Auggie.
- Tool selection rules exist for retrieve, map, and grep.
- Wiki behavior remains unchanged.
- Grok Search remains external/current-only.
- CP0 guard tests reject active Auggie references.
- Fast skill suite passes.
- Plugin version is bumped for release visibility.
