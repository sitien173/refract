# Block Executor Failures Implementation Plan

## Phase Table

| Phase | Owner | Outcome |
| --- | --- | --- |
| 1 | `codex` | Core CCG workflow blocks on executor MCP failures and has no fallback evidence path |
| 2 | `codex` | User-facing skill/docs/hooks match blocking policy |

### Phase 1: Core workflow blocks on MCP failures

**Owner:** `codex`

**Goal:** Remove fallback/retry executor behavior from coordinating-multi-model-work and make all Codex/Gemini MCP failures produce `BLOCKED`.

**Files:**
- Modify: `skills/coordinating-multi-model-work/SKILL.md`
- Modify: `skills/coordinating-multi-model-work/checkpoints.md`
- Modify: `skills/coordinating-multi-model-work/GATE.md`
- Modify: `skills/coordinating-multi-model-work/context-sharing.md`
- Modify: `skills/coordinating-multi-model-work/prompts/gemini-base.md`
- Delete: `skills/coordinating-multi-model-work/prompts/sonnet-fallback-base.md`

**Tasks:**
1. Delete Sonnet fallback prompt template.
2. Replace Gemini fallback, Codex retry, and Claude-code/Sonnet fallback rules with immediate `BLOCKED` handling for `timeout`, `tool-unavailable`, `session-failed`, session instability, and `permission-blocked`.
3. Remove live `FALLBACK` evidence format and replace it with one `BLOCKED` evidence block covering all MCP failure reasons.
4. Remove stale Sonnet fallback/session-memory wording from context-sharing and Gemini prompt text.

**Acceptance Criteria:**
- Core CCG docs contain no live instruction to retry Codex, fall back from Gemini to Codex, or dispatch Claude-code/Sonnet after executor MCP failure.
- `BLOCKED` evidence format exists for all executor MCP failure reasons.
- Deleted Sonnet fallback prompt has no live references outside historical plan/design text.

**Reviewer Checklist:**
- Spec requires immediate blocking on any Codex/Gemini MCP failure.
- Historical plan `docs/plans/2026-04-06-sonnet-fallback-strategy-design.md` remains unchanged.
- Wording still distinguishes executor MCP failures from CP4 `FAIL` review follow-ups.

**Integration Checks:**
- `rtk rg "sonnet-fallback-base|Claude-code/Sonnet|Status: FALLBACK|retry once|Gemini fails.*fall back|Codex fails.*fall back" skills/coordinating-multi-model-work skills/shared skills/executing-plans skills/executing-phases hooks README.md superpowers-ccg.md`
- Confirm any remaining matches are intentional non-live historical/design references only.

### Phase 2: Public workflow wording matches blocking policy

**Owner:** `codex`

**Goal:** Update skills, hooks, README, and top-level docs so users see fail-closed behavior instead of fallback behavior.

**Files:**
- Modify: `skills/shared/multi-model-integration-section.md`
- Modify: `skills/executing-plans/SKILL.md`
- Modify: `skills/executing-phases/SKILL.md`
- Modify: `hooks/session-start.sh`
- Modify: `hooks/user-prompt-submit.sh`
- Modify: `README.md`
- Modify: `superpowers-ccg.md`

**Tasks:**
1. Replace shared integration fallback section with fail-closed executor MCP failure policy.
2. Update executing skills so routing rules say MCP failure blocks the phase; keep CP4 review-loop wording for spec failures only.
3. Update hook prompt text to inject current blocking policy instead of fallback policy.
4. Update README/top-level CCG overview to remove practical fallback claims.

**Acceptance Criteria:**
- User-facing live docs consistently say Codex/Gemini MCP failures block the phase.
- No live docs claim Gemini falls back to Codex or Claude-code.
- No live docs claim Codex retries then falls back to Sonnet/Claude-code.

**Reviewer Checklist:**
- Wording remains concise and consistent across skills/hooks/docs.
- Supplementary-tool fallback wording unrelated to executor MCP failure is not changed unless necessary.
- Existing executing-phases tests about CP4 review, single executor ownership, session reuse, and ERP still make sense.

**Integration Checks:**
- `rtk rg "fallback|fall back|Claude-code|Sonnet|retry once|FALLBACK" skills hooks README.md superpowers-ccg.md tests/claude-code`
- Inspect remaining matches and separate allowed generic/historical/test wording from stale executor fallback policy.

## Final Integration

After all phases pass:

1. Run final stale-reference search:
   - `rtk rg "sonnet-fallback-base|Claude-code/Sonnet|Status: FALLBACK|Gemini fails.*fall back|Codex fails.*fall back|retry once" .`
2. Confirm remaining matches are limited to:
   - `docs/plans/2026-04-06-sonnet-fallback-strategy-design.md`
   - `docs/plans/2026-05-04-block-executor-failures-design.md`
   - `docs/plans/2026-05-04-block-executor-failures-implementation-plan.md`
   - unrelated generic uses of fallback outside executor MCP policy
