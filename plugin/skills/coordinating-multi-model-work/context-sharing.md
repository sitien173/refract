# Smart Context Sharing

> **Canonical source.** This file is the single source of truth for the 3-tier prompt rules, budgets, `SESSION_POLICY` decision table, and Tier 3 freshness check. Other docs (`checkpoints.md`, `INTEGRATION.md`, `SKILL.md`, `prompts/codex-base.md`, `prompts/gemini-base.md`, `shared/protocol-threshold.md`, `shared/multi-model-integration-section.md`) restate parts of these rules for in-place legibility but must not diverge — when they conflict, this file wins.

This workflow uses orchestrator-managed smart context sharing to keep worker prompts narrow without losing important information.

## Core Model

1. CP0 decides whether `docs/wiki/` durable knowledge is useful, then selectively queries it when relevant.
2. CP0 uses Auggie to retrieve the minimum current local code context needed for routing.
3. The orchestrator stores the useful output as small reusable `CONTEXT_ARTIFACTS`.
4. CP1 chooses `SESSION_POLICY` for the next executor turn: `FRESH` for Tier 1, or `CONTINUE` for Tier 3 when the next phase stays with the same worker and subsystem.
5. CP2 uses a 3-tier prompt system:
   - Tier 1 initial call: `Task`, `Phase`, `Context`, `Files`, `Done When`, and full ERP v1.1
   - Tier 2 same-phase follow-up: `SESSION_ID`, `FIX`, `DELTA_FILES`, `DELTA_CONTEXT`
   - Tier 3 cross-phase continuation: `SESSION_ID`, `SESSION_POLICY: CONTINUE`, `PHASE`, `New Phase`, `New/Changed Files`, `Delta Context`, `Done When`
5. If the same worker session continues, send only the minimum delta context needed for that tier.

## Artifact Guidelines

Good artifact ids are short, stable, and reusable:

- `req/core`
- `req/non_goals`
- `files/hotspots`
- `files/owners`
- `api/contracts`
- `ui/patterns`
- `verify/command`
- `debt/known`
- `research/notes`
- `debug/root_cause`
- `wiki/relevant`
- `wiki/decisions`
- `wiki/conflicts`
- `wiki/sources`

Wiki artifacts come from selective `docs/wiki/` lookup only. They are advisory and citation-backed; current files, tests, and current user requests override them.

Each artifact should contain one focused piece of information, not a narrative dump.

## Smart Context Budget

Claude owns the context graph. Executors receive only the minimum phase-scoped context needed to implement the active phase.

Budget rows below use two terms with distinct force:

- **target** — soft goal; exceeding it is a signal to narrow the phase or shrink hydrated snippets, not an error.
- **limit** — hard ceiling; do not exceed.

| Context Item | Budget |
| --- | --- |
| Tier 1: Initial call | target ≤ 1500 tokens |
| Tier 2: Same-phase follow-up | target ≤ 400 tokens |
| Tier 3: Cross-phase continuation | target ≤ 600 tokens |
| `HYDRATED_CONTEXT` | **limit** ≤ 300 tokens |

Budget rules:

- Keep reusable artifact ids inside Claude's context graph. Workers should receive only the hydrated facts they need for the current tier.
- `HYDRATED_CONTEXT` contains existing code snippets, repo facts, command output summaries, or artifact excerpts only.
- `HYDRATED_CONTEXT` may include citation-backed wiki excerpts, but never full `docs/wiki/` pages or raw source dumps.
- Never pre-write new implementation inside `HYDRATED_CONTEXT`.
- Do not send full files unless the file is very small or the phase explicitly requires whole-file replacement.
- If the budget is exceeded, narrow the phase or replace snippets with smaller artifact excerpts.

Refresh local context only when:

- file ownership changes
- integration checks fail
- a worker creates a new API used by later phases
- reviewer finds architecture drift
- the next phase touches an unread subsystem

## Tier 1: Initial Call

First call to a worker on a new session:

```text
## Task
[compressed original request]

## Phase
TASK_ID: phase_02
SESSION_POLICY: FRESH

## Context
- [short snippet from req/core]
- [short snippet from files/hotspots]
- [short snippet from verify/command]

## Files
- [explicit file set]

## Done When
- [merged success criteria and reviewer checklist items]

## Response Protocol
[full ERP v1.1 block]
```

## Tier 2: Same-Phase Follow-Up

When reusing the same worker `SESSION_ID` on the same phase, do not resend the whole bundle. Send only the structured delta:

```text
SESSION_ID: {id}
FIX: {what failed or what gap remains}
DELTA_FILES: {only files changed since the last worker call, or none}
DELTA_CONTEXT: {only new snippets or facts needed for the fix, or none}
Respond using ERP v1.1
```

Rules:

- `FIX` is mandatory and should state the exact missing behavior or failed check.
- `DELTA_FILES` is only for files created or changed after the previous worker turn.
- `DELTA_CONTEXT` is only for new facts the worker did not already have.
- Do not exceed 2 Tier-2 follow-ups on the same phase. If the phase still fails after 2, re-scope or escalate.

## Tier 3: Cross-Phase Continuation

When CP1 routes a new related phase to the same worker, reuse the `SESSION_ID` with `SESSION_POLICY: CONTINUE` and send only the new phase delta:

```text
SESSION_ID: {id}
SESSION_POLICY: CONTINUE
PHASE: phase_03

## New Phase
[one-sentence phase summary]

## New/Changed Files
- [only files not already known to the worker]

## Delta Context
- [only new patterns, APIs, constraints, or findings]

## Done When
- [new phase checklist]

Respond using ERP v1.1
```

Use this decision table at CP1. Evaluate top-down; first match wins.

| # | Condition | SESSION_POLICY |
| --- | --- | --- |
| 1 | Different worker than the prior phase | `FRESH` |
| 2 | Previous phase ended `FAIL` after 2 Tier-2 retries | `FRESH` |
| 3 | Same worker AND new phase touches ≥1 file from the prior phase's file set | `CONTINUE` |
| 4 | Same worker AND no file overlap, but same subsystem (same top-level dir or shared module boundary) | `CONTINUE` |
| 5 | Otherwise | `FRESH` |

### Tier 3 freshness check (mandatory)

Before dispatching Tier 3, verify that no file the worker is assumed to "remember" has been modified outside the worker session (human edits, `git pull`, sibling agent). For each file the prior worker touched:

- If its content hash differs from the version the worker last produced, force-include that file's current content (or a delta excerpt) in `New/Changed Files`.
- If more than half the prior file set has changed, prefer Tier 1 (`SESSION_POLICY: FRESH`) over Tier 3 — the worker's session memory is no longer a reliable anchor.

The worker has no way to detect external edits on its own; skipping this check silently poisons the continuation.

## Worker Output

Workers still return External Response Protocol v1.1, but they may also emit:

```text
## CONTEXT ARTIFACTS
- id: debug/root_cause
  summary: Race condition in token refresh before assertion
```

These artifacts can then be reused by later tasks instead of rediscovering the same information.

## Anti-Patterns

### Do NOT pre-write implementation in HYDRATED_CONTEXT

`HYDRATED_CONTEXT` is for existing code context only. Pre-writing new file contents here is the worker's job — doing it inflates prompts 10–20× with no benefit.

**Wrong** — pre-written file contents:
```text
HYDRATED_CONTEXT:
- package.json: { "name": "my-app", "scripts": { "dev": "vite" }, "dependencies": { ... full 40-line file ... } }
- vite.config.ts: import { defineConfig } from "vite"; export default defineConfig({ ... full file ... })
- tsconfig.json: { "compilerOptions": { "target": "ES2020", ... full file ... } }
```

**Correct** — greenfield task, no existing code:
```text
HYDRATED_CONTEXT:
- Existing directory: .git/, docs/ — do not modify
- No source files exist yet
```

**Correct** — modification task, existing patterns:
```text
HYDRATED_CONTEXT:
- src/api/auth.ts line 42: uses `withRetry(fn, 3)` pattern for all external calls
- Error type convention: throw `AppError` with `{ code, message, context }` shape
```

Keep `HYDRATED_CONTEXT` under 300 tokens hard cap. If you are over that, you are over-specifying.
