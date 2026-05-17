---
name: coordinating-multi-model-work
description: "Three-gate workflow (Plan → Execute → Review). Claude handles simple tasks directly; Codex owns back-end/data/infra; Gemini owns front-end. CROSS_VALIDATION mandatory before planning any new feature or ideation."
---

# Coordinating Multi-Model Work

Claude plans, routes, reviews, integrates, and handles simple tasks directly. Codex owns back-side (backend, database, system, infra, CI/CD, scripts). Gemini owns front-side (UI, CSS, motion, canvas/SVG, multimodal, large-context sweeps). Workers edit files via their own write tools.

## Gates

### 1. Plan

- **New feature / ideation / proposal** → run **CROSS_VALIDATION** first (Codex + Gemini narrow question), reconcile divergences, then plan. Mandatory before any planning gate for new work.
- Gather minimum context needed to route. Use any tool that fits (Read, Grep, Glob, Bash, prior knowledge). Skip ceremony for trivial tasks.
- Frame work as one phase with 2–4 related tasks, file set, and `Done When` checks (build/lint/test).
- Decide owner by **side**, not by default. Output the routing block:

```text
# ROUTE
- Owner: Claude | Codex | Gemini | Cross-Validation
- Reason: [one line — back-side / front-side / simple / new-feature ideation]
- Done When: [build/test/lint commands or acceptance bullets]
```

**Routing rules (side-based):**

| Phase | Owner |
|---|---|
| Simple/trivial task Claude can do directly (one-line edit, rename, doc tweak, single-file fix, clarification) | Claude |
| **Back-side**: backend, API, business logic, database, ORM, system, infra, CI/CD, Docker, scripts, server-side tests, debugging back-end | Codex |
| **Front-side**: UI components, CSS, layout, motion, canvas/SVG, client-side interactions, multimodal input, front-end tests, >200K-token UI/doc sweeps | Gemini |
| New feature, ideation, proposal, design exploration (before plan exists) | **Cross-Validation** (Codex + Gemini) → reconcile → assign side owner |
| Full-stack phase spanning both sides | Split into back-side + front-side sub-phases; route each |
| Ambiguous side | Ask user |

### 2. Execute

- **Claude-owned (simple):** edit directly with built-in tools.
- **Codex / Gemini:** call `mcp__codex__codex` / `mcp__gemini__gemini`. Send: task summary, files, `Done When`, and minimum hydrated context (no full files, no pre-written implementation).
- **Cross-Validation:** ask Codex and Gemini the same narrow question, compare answers, pick a direction, then route implementation to the side owner. Do not run two parallel implementations.
- Worker edits files via MCP write tools. Response must list every changed file under `## FILES MODIFIED`.
- **Same-phase fix:** reuse `SESSION_ID`, send only `FIX:` + delta context.
- **MCP failure** (timeout, unavailable, session-failed, permission-blocked, prompt too long) → output `BLOCKED`, ask user. No retry, no executor switch, no Task/Agent fallback without explicit consent.
- **Long input** (>~8KB, >1500 tokens): write to a repo file (prefer `docs/plans/`), pass the path. Never paste raw guides/specs/research into the MCP `PROMPT`.

**Worker response format:**

```text
# EXTERNAL RESPONSE

## SUMMARY
[one sentence]

## FILES MODIFIED
| Action  | Path     | Change |
|---------|----------|--------|
| Created | src/...  | ...    |
| Edited  | src/...  | ...    |

## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: [one line]

## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE
```

### 3. Review

Two sub-steps: **(a) Spec** → **(b) Quality**.

**(a) Spec & Integration**

- Run the phase's `Done When` checks (build/lint/test).
- Compare result vs original request, file scope, integration output.
- Initial status: `PASS` | `PASS_WITH_DEBT` | `FAIL`.

**(b) Quality scan**

- Scan every file in `## FILES MODIFIED` for:

| Category | Check |
|---|---|
| Edge cases | null/undefined, empty arrays, boundaries, off-by-one |
| Error handling | swallowed errors, missing catch, unhandled rejections |
| Security | injection (SQL/XSS/cmd), hardcoded secrets, unsafe deserialization, missing input validation at boundaries |
| Naming & clarity | misleading names, ambiguous abbreviations, functions doing more than the name says |
| Duplication | copy-paste logic that should be extracted |
| Correctness | logic errors, race conditions, resource leaks, bad type narrowing |

- Severity → status downgrade:

| Severity | Effect |
|---|---|
| CRITICAL — bug, security vuln, data-loss risk | Force `FAIL` |
| HIGH — likely bug or significant quality gap | Force `FAIL` |
| MEDIUM — code smell, missed edge case, unclear logic | Downgrade `PASS` → `PASS_WITH_DEBT` |
| LOW — minor naming, style, small duplication | Noted only |

- Skip Quality scan when: phase is docs/coordination only, owner was Claude on a one-line/trivial edit, or `## FILES MODIFIED` is empty. Required for every Codex / Gemini phase.
- Findings that contradict user's explicit request or project conventions are discarded with explanation.

**Output:**

```text
# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Quality Findings:
  | Severity | path:line | Problem | Fix |
  |----------|-----------|---------|-----|
  (or "No findings" / "Skipped: <reason>")
- Final Status: PASS | PASS_WITH_DEBT | FAIL
- Explanation: [one line — what changed from spec status and why]
- Next: [done | debt + owner | retry/clarify]
```

- `PASS_WITH_DEBT` requires explicit non-blocking debt note (spec or MEDIUM quality).
- `FAIL` blocks completion: re-route the gap or ask user.
- Quality scan stays scoped to the changed files — no broader audit.

## Cross-Validation Output

```text
# CROSS-VALIDATION
- Agreement: [shared conclusions]
- Divergences: [one line per disagreement + chosen resolution]
- Next owner: Codex | Gemini | Claude
```

## Session-Resume Artifacts

Plans that span multiple Claude sessions persist three files alongside the plan doc. Resume artifacts are opt-in per plan; flat single-file plans need none.

### `.sessions.json` — worker session cache

```json
{
  "schema_version": 1,
  "plan_path": "docs/plans/<slug>",
  "current_phase": 2,
  "phase_owner": "codex",
  "sessions": {
    "codex":  "<SESSION_ID or null>",
    "gemini": "<SESSION_ID or null>"
  },
  "last_updated": "<ISO8601>"
}
```

- Read on plan load + before every MCP call.
- Write after every MCP call that returns a `SESSION_ID`.
- No TTL. MCP rejection is the only invalidation signal.
- Cache miss → fresh session allowed.
- Cache present but rejected by MCP → `BLOCKED`. User clears the offending id (`rm` file or edit) before retry.
- Gitignored — local worker state, not durable repo content.

### `.handover.md` — terse resume pointer

≤500 tokens. Frontmatter + body. Always Claude-authored at end of every turn that changes plan state (route set, phase change, BLOCKED, phase done). Hook cannot synthesize.

```markdown
---
plan: docs/plans/<slug>
updated_at: <ISO8601>
current_phase: <N>
status: ACTIVE   # ACTIVE | BLOCKED | DONE
owner: claude | codex | gemini
session_refs:
  codex: <id or null>
  gemini: <id or null>
---

## next_action
<one to three sentences — exact next step>

## read_first
- docs/plans/<slug>/PHASE-<N>.md

## blockers
<empty | one line per blocker>

## decisions_delta
<empty | new decisions since prior handover>

## uncommitted_files
<empty | paths edited but not yet reviewed>
```

### `PHASE-<N>.md` — durable phase journal

Created at phase start with Route skeleton. Finalized immediately after the Review gate.

```markdown
# Phase <N> — <title>

- Status: ACTIVE | DONE | BLOCKED
- Owner: Claude | Codex | Gemini
- Started: <ISO>
- Finished: <ISO>

## Route
- Reason: ...
- Done When: ...
- Files: ...

## Files Modified
| Action | Path | Change |

## Review
- Spec Status: ...
- Quality Findings: ...
- Final Status: ...

## Decisions
- <decision>: <rationale> → <impact>

## Handoff
<what next phase or new session must do>
```

### Resume rule

New session reads `.handover.md` first, then only the files listed in `read_first`. Never scans every `PHASE-<N>.md` unless the handover is missing or corrupt.

## Hard Rules

- One phase, one primary owner, one review.
- No draft-then-reimplement handoffs — worker output is the final edit.
- Cross-Validation is **mandatory for new features / ideation / proposals before planning**; otherwise skip it.
- Route by side (back vs front), not by default — never auto-route to one executor.
- User overrides ("use Codex" / "use Gemini" / "no external models" / "skip cross-validation") win.
