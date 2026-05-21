---
name: coordinating-multi-model-work
description: "Three-gate workflow (Plan → Execute → Review). Claude handles simple tasks directly; Codex owns back-end/data/infra; Gemini owns front-end. CROSS_VALIDATION mandatory before planning any new feature or ideation."
---

# Coordinating Multi-Model Work

Claude plans, routes, reviews, integrates, handles simple tasks directly. Codex owns back-side (backend, database, system, infra, CI/CD, scripts). Gemini owns front-side (UI, CSS, motion, canvas/SVG, multimodal, large-context sweeps). Workers edit files via own write tools.

## Gates

### 1. Plan

- **New feature / ideation / proposal** → run **CROSS_VALIDATION** first (Codex + Gemini narrow question), reconcile divergences, then plan. Mandatory before any planning gate for new work.
- Gather minimum context needed to route. Use any fitting tool (Read, Grep, Glob, Bash, prior knowledge). Skip ceremony for trivial tasks.
- Frame work as one phase: 2–4 related tasks, file set, `Done When` checks (build/lint/test).
- Decide owner by **side**, not default. Output routing block:

```text
# ROUTE
- Owner: Claude | Codex | Gemini | Cross-Validation
- Reason: [one line — back-side / front-side / simple / new-feature ideation]
- Done When: [build/test/lint commands or acceptance bullets]
```

**Routing rules (side-based):**

| Phase | Owner |
|---|---|
| Simple/trivial task Claude handles directly (one-line edit, rename, doc tweak, single-file fix, clarification) | Claude |
| **Back-side**: backend, API, business logic, database, ORM, system, infra, CI/CD, Docker, scripts, server-side tests, back-end debugging | Codex |
| **Front-side**: UI components, CSS, layout, motion, canvas/SVG, client-side interactions, multimodal input, front-end tests, >200K-token UI/doc sweeps | Gemini |
| New feature, ideation, proposal, design exploration (before plan exists) | **Cross-Validation** (Codex + Gemini) → reconcile → assign side owner |
| Full-stack phase spanning both sides | Split into back-side + front-side sub-phases; route each |
| Ambiguous side | Ask user |

### 2. Execute

- **Claude-owned (simple):** edit directly with built-in tools.
- **Codex / Gemini:** call `mcp__openmcp__run` with `backend="codex"` (back-side) or `backend="agy"` (front-side, Gemini via Antigravity CLI). Send: task summary, files, `Done When`, minimum hydrated context (no full files, no pre-written implementation). Default `debug=False` — worker writes its own `responses/phase-<N>.md`, no need to inflate the MCP reply.
- **Cross-Validation:** ask Codex and Gemini same narrow question, compare answers, pick direction, route implementation to side owner. No two parallel implementations.
- Worker edits files via MCP write tools. Response must list every changed file under `## FILES MODIFIED`.
- **Same-phase fix:** reuse `SESSION_ID`, send only `FIX:` + delta context.
- **MCP failure** (timeout, unavailable, session-failed, permission-blocked, prompt too long) → output `BLOCKED`, ask user. No retry, no executor switch, no Task/Agent fallback without explicit consent.
- **Prompt-to-file by default:** write every dispatch prompt to `docs/plans/<slug>/prompts/<task-id>.md` and pass that path to the worker. Inline-in-MCP-`PROMPT` allowed only for one- or two-sentence asks with no context block.

**Per-task git commits (required for Codex / Gemini phases):**

- Worker commits its own changes per task — one commit per task in the phase, message prefix `phase-<N>.task-<M>: <summary>`.
- Worker returns commit hashes in `## COMMITS`. Claude does not commit on the worker's behalf.
- Claude reviews diff via `git show <hash>` per task during the Review gate.
- Claude-owned simple edits: commit per logical change, no enforced format.

**Per-task decision notes (required for Codex / Gemini phases):**

Worker writes `docs/plans/<slug>/notes/phase-<N>.task-<M>.md` capturing anything outside the spec:

```markdown
# phase-<N>.task-<M> — Decision Note

## Decisions made (not in spec)
- <decision>: <why>

## Spec deviations
- <what changed vs Phase doc>: <why>

## Tradeoffs accepted
- <tradeoff>: <alternative rejected + reason>

## Assumptions
- <assumption>

## Follow-ups for human
- <thing the human should know>
```

Empty sections written as `- none`. File required even when all sections are `none` (proves worker considered each).

**Phase response file (required for Codex / Gemini phases):**

After all tasks in the phase are done, worker writes the full `# EXTERNAL RESPONSE` block to `docs/plans/<slug>/responses/phase-<N>.md` in addition to returning it inline. One file per phase — it already aggregates per-task commits. Survives session compaction.

**Worker response format:**

```text
# EXTERNAL RESPONSE

## META
- Phase: <N>
- Owner: codex | gemini
- SessionID: <id>
- Started: <ISO8601>
- Finished: <ISO8601>
- Plan dir: docs/plans/<slug>

## SUMMARY
[one sentence]

## FILES MODIFIED
| Action  | Path     | Change |
|---------|----------|--------|
| Created | src/...  | ...    |
| Edited  | src/...  | ...    |

## COMMITS
- phase-<N>.task-<M>: <hash>  <subject>
- phase-<N>.task-<M+1>: <hash>  <subject>

## NOTES
- notes/phase-<N>.task-<M>.md
- notes/phase-<N>.task-<M+1>.md

## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: [one line]

## CLARIFICATIONS NEEDED
None (or list questions; emit and stop if any)

## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE
```

Final worker line (after the `# EXTERNAL RESPONSE` block):

```text
Phase <N> completed. Response file: docs/plans/<slug>/responses/phase-<N>.md.
```

Single-line trigger Claude scans for; all structured fields (commits, session id, notes, owner) already live in `## META` / `## COMMITS` / `## NOTES`, so the line stays terse.

### 3. Review

Two sub-steps: **(a) Spec** → **(b) Quality**.

**(a) Spec & Integration**

- Run phase's `Done When` checks (build/lint/test).
- Compare result vs original request, file scope, integration output.
- Initial status: `PASS` | `PASS_WITH_DEBT` | `FAIL`.

**(b) Quality scan**

- Scan every file in `## FILES MODIFIED` for:

| Category | Check |
|---|---|
| Edge cases | null/undefined, empty arrays, boundaries, off-by-one |
| Error handling | swallowed errors, missing catch, unhandled rejections |
| Security | injection (SQL/XSS/cmd), hardcoded secrets, unsafe deserialization, missing input validation at boundaries |
| Naming & clarity | misleading names, ambiguous abbreviations, functions doing more than name says |
| Duplication | copy-paste logic that should be extracted |
| Correctness | logic errors, race conditions, resource leaks, bad type narrowing |

- Severity → status downgrade:

| Severity | Effect |
|---|---|
| CRITICAL — bug, security vuln, data-loss risk | Force `FAIL` |
| HIGH — likely bug or significant quality gap | Force `FAIL` |
| MEDIUM — code smell, missed edge case, unclear logic | Downgrade `PASS` → `PASS_WITH_DEBT` |
| LOW — minor naming, style, small duplication | Noted only |

- Skip Quality scan when: phase is docs/coordination only, owner was Claude on one-line/trivial edit, or `## FILES MODIFIED` empty. Required for every Codex / Gemini phase.
- Findings contradicting user's explicit request or project conventions discarded with explanation.

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
- `FAIL` blocks completion: re-route gap or ask user.
- Quality scan stays scoped to changed files — no broader audit.

## Cross-Validation Output

```text
# CROSS-VALIDATION
- Agreement: [shared conclusions]
- Divergences: [one line per disagreement + chosen resolution]
- Next owner: Codex | Gemini | Claude
```

## Session-Resume Artifacts

Plans spanning multiple Claude sessions persist three files alongside plan doc. Resume artifacts opt-in per plan; flat single-file plans need none.

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
- Write after every MCP call returning `SESSION_ID`.
- No TTL. MCP rejection only invalidation signal.
- Cache miss → fresh session allowed.
- Cache present but MCP rejects → `BLOCKED`. User clears offending id (`rm` file or edit) before retry.
- Gitignored — local worker state, not durable repo content.

### `.handover.md` — terse resume pointer

≤500 tokens. Frontmatter + body. Always Claude-authored at end of every turn changing plan state (route set, phase change, BLOCKED, phase done). Hook cannot synthesize.

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

## completed_tasks
- id: phase-<N>.task-<M>
  owner: codex | gemini | claude
  commit: <hash>
  note: docs/plans/<slug>/notes/phase-<N>.task-<M>.md
- (one row per task; phase response file lives at responses/phase-<N>.md)

## blockers
<empty | one line per blocker>

## decisions_delta
<empty | new decisions since prior handover>

## uncommitted_files
<empty | paths edited but not yet committed by worker>
```

### Plan directory layout

```
docs/plans/<slug>/
  PLAN.md
  PHASE-<N>.md
  .handover.md
  .sessions.json          # gitignored — worker session id cache
  prompts/phase-<N>.md    # dispatch prompt, per phase (per-task only when fanning out)
  notes/phase-<N>.task-<M>.md   # decision note, per task
  responses/phase-<N>.md  # EXTERNAL RESPONSE, per phase
```

`prompts/`, `notes/`, `responses/` are committed alongside `PLAN.md` — they are the durable audit trail.

### `PHASE-<N>.md` — durable phase journal

Created at phase start with Route skeleton. Finalized immediately after Review gate.

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

## Commits
- phase-<N>.task-<M>: <hash>  <subject>

## Review
- Spec Status: ...
- Quality Findings: ...
- Final Status: ...

## Decisions
- See `notes/phase-<N>.task-*.md` for per-task decisions. Cross-task or phase-level decisions noted here only.

## Handoff
<what next phase or new session must do>
```

### Resume rule

New session reads `.handover.md` first, then only files listed in `read_first`. Never scans every `PHASE-<N>.md` unless handover missing or corrupt.

## Hard Rules

- One phase, one primary owner, one review.
- No draft-then-reimplement handoffs — worker output is final edit.
- Cross-Validation **mandatory for new features / ideation / proposals before planning**; otherwise skip.
- Route by side (back vs front), not default — never auto-route to one executor.
- One commit per task by the worker; missing commit hashes in `## COMMITS` block Review.
- Per-task decision note + response file written before worker emits the final completion line.
- Dispatch prompts written to `prompts/<task-id>.md` by default; inline only for trivial one-liner asks.
- User overrides ("use Codex" / "use Gemini" / "no external models" / "skip cross-validation") win.