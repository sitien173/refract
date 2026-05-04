# Tiered Prompt Architecture — Smart Context v2

**Date:** 2026-04-17
**Goal:** Redesign the CP2 prompt pipeline into three session-aware tiers, add cross-phase session continuity, structured delta format, and reduce total token usage by ~75%.

---

## Problem

The current CP2 prompt template is monolithic. Every call — initial, follow-up, or new phase — sends the same verbose structure (~2500 tokens) regardless of what the worker already knows. Key waste:

- Response protocol boilerplate (~200 tokens) repeated every call
- User request + phase summary + success criteria overlap (~150 tokens)
- Reviewer checklist + integration checks sent to workers but only used by Claude (~100 tokens)
- No structured delta format for follow-ups (vague 7-item checklist)
- No cross-phase session reuse (always starts fresh even when same worker handles related phases)

---

## Design Decisions

| Decision | Current | New |
|---|---|---|
| Template structure | 1 monolithic template | 3 tiers (initial, fix, cross-phase) |
| Success Criteria + Reviewer Checklist | Two separate sections | Merged into "Done When" |
| Integration Checks | Sent to worker | Claude-only, kept at CP4 |
| User Request + Phase Summary | Both sent (redundant) | Single "Task" + "Phase" block |
| Context Refs | Separate section | Folded into hydrated context |
| ERP v1.1 boilerplate | Every call (~200 tokens) | First call only; "Respond using ERP v1.1" on follow-ups |
| Follow-up format | Vague 7-item checklist | Structured 4-field delta template |
| Cross-phase sessions | Always FRESH | CONTINUE when same worker + related subsystem |
| SESSION_POLICY | Not in CP1 | New field in CP1 Route block |
| Max follow-ups per phase | Unlimited | Max 2 Tier-2, then escalate |

---

## Tier 1: Initial Call

First call to a worker on a new session. Full context, full response protocol.

**Budget: <= 1500 tokens (down from ~2500)**

```text
## Task
{compressed_user_request — 1-2 sentences}

## Phase
TASK_ID: {task_id}
SESSION_POLICY: FRESH
{task_summary — 1 sentence}

## Context
{hydrated_context — existing code snippets only, <= 300 tokens}

## Files
{flat file list}

## Done When
- [ ] {merged success criteria + reviewer checklist items}

## Response Protocol
[full ERP v1.1 block — sent only here]
```

### What changed vs current template

- Removed `Context Refs` as a separate section (folded into hydrated context)
- Removed `Integration Checks` (Claude-only concern, kept at CP4)
- Merged `Success Criteria` + `Reviewer Checklist` into `Done When`
- Removed `Original User Request` + `CP1 Phase Summary` redundancy — single `Task` + `Phase` replaces both
- ~530 tokens of overhead eliminated

---

## Tier 2: Same-Phase Follow-Up (Delta Fix)

When CP4 returns `FAIL` or the worker said `CONTINUE_SESSION`, reuse the same `SESSION_ID` and send only what changed.

**Budget: <= 400 tokens**

```text
SESSION_ID: {id}
FIX: {what failed — CP4 explanation or specific gap}
DELTA_FILES: {only new/changed files since last call, if any}
DELTA_CONTEXT: {only new snippets needed, if any — omit if none}
Respond using ERP v1.1
```

### Rules

- `FIX` is mandatory — it is the one thing the worker needs to act on
- `DELTA_FILES` only if Claude created/modified files between calls (e.g., another worker touched a shared file)
- `DELTA_CONTEXT` only if the worker needs a new snippet it did not have before
- No response protocol boilerplate — worker already has it from Tier 1
- Max 2 Tier-2 follow-ups per phase. If still failing after 2, escalate: re-scope or ask user

### Example

```text
SESSION_ID: codex_abc123
FIX: retry logic missing — fetchUser must use withRetry(fn, 3) with exponential backoff
DELTA_FILES: none
DELTA_CONTEXT: none
Respond using ERP v1.1
```

~50 tokens vs ~1000 tokens today.

---

## Tier 3: Cross-Phase Continuation

When CP1 routes the next phase to the same worker AND judges the phases as related, reuse the `SESSION_ID` with a lightweight handoff.

**Budget: <= 600 tokens**

```text
SESSION_ID: {id}
SESSION_POLICY: CONTINUE
PHASE: {new task_id}

## New Phase
{task_summary — 1 sentence}

## New/Changed Files
{only files not already known to the worker}

## Delta Context
{only new snippets — patterns, APIs, or constraints the worker does not have yet}

## Done When
- [ ] {new phase checklist}

Respond using ERP v1.1
```

### Decision Rule at CP1

| Condition | SESSION_POLICY |
|---|---|
| Same worker + overlapping files or same subsystem | `CONTINUE` |
| Same worker + different subsystem | `FRESH` |
| Different worker (e.g., Codex to Gemini) | `FRESH` (always) |
| Previous phase CP4 was `FAIL` after 2 retries | `FRESH` (reset drift) |

### Example

```text
SESSION_ID: codex_abc123
SESSION_POLICY: CONTINUE
PHASE: phase_02

## New Phase
Add integration tests for the /users CRUD endpoints you just built.

## New/Changed Files
tests/api/users.test.ts (create)

## Delta Context
- Test runner: vitest with supertest for HTTP
- Existing test pattern: see tests/api/health.test.ts

## Done When
- [ ] covers GET/POST/PUT/DELETE for /users
- [ ] tests run with rtk npx vitest
- [ ] uses existing test patterns from health.test.ts

Respond using ERP v1.1
```

~120 tokens vs ~2500 tokens today.

---

## Updated CP1 Output Format

The CP1 routing block gets one new field — `Session-Policy`:

```text
# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the phase]

## Route
- Model: Codex
- Cross-Validation: No
- Session-Policy: CONTINUE / FRESH
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

`Session-Policy` defaults to `FRESH` when omitted (backward compatible).

---

## Updated Budget Targets

| Prompt Tier | Current Budget | New Budget | Typical Actual |
|---|---|---|---|
| Tier 1: Initial call | <= 2500 tokens | <= 1500 tokens | ~800-1200 |
| Tier 2: Same-phase fix | <= 1000 tokens | <= 400 tokens | ~50-200 |
| Tier 3: Cross-phase continue | N/A (always fresh) | <= 600 tokens | ~100-300 |
| HYDRATED_CONTEXT | <= 800, pref 300 | <= 300 tokens (hard cap) | ~50-200 |

---

## Estimated Token Savings

For a typical 3-phase project where phase_02 and phase_03 continue from phase_01:

| Step | Current | New | Savings |
|---|---|---|---|
| Phase 1 (initial) | ~2500 | ~1200 | 1300 |
| Phase 1 fix (1 retry) | ~1000 | ~150 | 850 |
| Phase 2 (continuation) | ~2500 | ~400 | 2100 |
| Phase 3 (continuation) | ~2500 | ~400 | 2100 |
| **Total** | **~8500** | **~2150** | **~6350 (75%)** |

---

## Implementation Phases

### Phase 1: Core Templates (Codex)

Update the prompt templates to the 3-tier structure.

**Files:**
- `skills/coordinating-multi-model-work/prompts/codex-base.md`
- `skills/coordinating-multi-model-work/prompts/gemini-base.md`

**Tasks:**
1. Replace the monolithic Phase Implementation Template with Tier 1 template
2. Add Tier 2 (delta fix) template
3. Add Tier 3 (cross-phase continuation) template
4. Update prompt discipline section with new budget targets and "Done When" guidance

**Done When:**
- [ ] Three distinct templates present in both codex-base.md and gemini-base.md
- [ ] Tier 1 has no reviewer checklist, no integration checks, uses "Done When"
- [ ] Tier 2 has exactly 4 fields: SESSION_ID, FIX, DELTA_FILES, DELTA_CONTEXT
- [ ] Tier 3 has SESSION_POLICY: CONTINUE and "New Phase" structure
- [ ] Budget targets updated in prompt discipline sections

**Integration Checks:**
- `rtk rg 'Done When' skills/coordinating-multi-model-work/prompts/` finds matches
- `rtk rg 'Tier 1|Tier 2|Tier 3' skills/coordinating-multi-model-work/prompts/` finds matches
- No `Reviewer Checklist` or `Integration Checks` sections inside the worker templates

---

### Phase 2: Context Sharing & Checkpoints (Codex)

Update the context sharing rules, checkpoint docs, and routing decision format.

**Files:**
- `skills/coordinating-multi-model-work/context-sharing.md`
- `skills/coordinating-multi-model-work/checkpoints.md`
- `skills/coordinating-multi-model-work/routing-decision.md`
- `skills/coordinating-multi-model-work/INTEGRATION.md`
- `skills/coordinating-multi-model-work/SKILL.md`

**Tasks:**
1. Rewrite context-sharing.md: replace Delta Follow-Ups with Tier 2 format, add Tier 3 cross-phase rules, update budget table
2. Add SESSION_POLICY field and decision table to routing-decision.md and checkpoints.md
3. Update INTEGRATION.md and SKILL.md to reference 3-tier system and new budgets
4. Add max 2 Tier-2 follow-ups rule to checkpoints.md

**Done When:**
- [ ] context-sharing.md has Tier 2 and Tier 3 templates with concrete examples
- [ ] routing-decision.md CP1 block includes `Session-Policy` field
- [ ] checkpoints.md documents SESSION_POLICY decision table
- [ ] HYDRATED_CONTEXT hard cap is 300 tokens everywhere
- [ ] Max 2 follow-ups rule is documented

**Integration Checks:**
- `rtk rg 'SESSION_POLICY' skills/coordinating-multi-model-work/` finds matches in routing-decision.md and checkpoints.md
- `rtk rg '300 tokens' skills/coordinating-multi-model-work/context-sharing.md` finds the hard cap
- No references to the old "7-item delta checklist" remain

---

### Phase 3: Hooks, Shared Docs & Rules (Codex)

Update the hook scripts, shared skill docs, and rules to reflect the new system.

**Files:**
- `hooks/user-prompt-submit.sh`
- `hooks/session-start.sh`
- `skills/shared/protocol-threshold.md`
- `skills/shared/multi-model-integration-section.md`
- `rules/bounded-tasks.mdc`

**Tasks:**
1. Update budget numbers in hooks (1500/400/600/300 instead of 2500/1000/800)
2. Add SESSION_POLICY reference to protocol-threshold.md CP1 format
3. Update multi-model-integration-section.md with cross-phase session rules
4. Update bounded-tasks.mdc with tier references and max follow-up rule

**Done When:**
- [ ] hooks reference new budget targets (1500, 400, 600, 300)
- [ ] protocol-threshold.md CP1 block includes Session-Policy
- [ ] bounded-tasks.mdc mentions 3-tier system
- [ ] No stale budget numbers (2500 executor, 1000 follow-up, 800 hydrated) remain in active docs

**Integration Checks:**
- `rtk rg '2500 tokens' hooks/ skills/shared/ rules/` returns zero matches
- `rtk rg '<= 1500 tokens' hooks/` finds matches
- `rtk rg 'Session-Policy' skills/shared/protocol-threshold.md` finds match

---

### Phase 4: Tests (Codex)

Update test assertions to verify the new patterns.

**Files:**
- `tests/claude-code/test-token-efficiency-guards.sh`

**Tasks:**
1. Update grep patterns to check for "Done When", "Tier 1/2/3", "SESSION_POLICY", new budget numbers
2. Remove assertions for old patterns (separate Reviewer Checklist in templates, 2500 budget)
3. Add assertion that worker templates do not contain Integration Checks

**Done When:**
- [ ] Tests pass with `rtk ./tests/claude-code/run-skill-tests.sh --test test-token-efficiency-guards.sh`
- [ ] Tests verify SESSION_POLICY presence
- [ ] Tests verify "Done When" pattern
- [ ] Tests verify no Integration Checks in worker templates

**Integration Checks:**
- Full test suite: `rtk ./tests/claude-code/run-skill-tests.sh`
