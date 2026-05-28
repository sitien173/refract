---
name: coordinating-multi-model-work
description: "Three-gate workflow (Plan → Execute → Review)"
---

# Coordinating Multi-Model Work

Claude plans, routes, reviews, integrates, handles simple tasks directly. Codex owns back-side (backend, database, system, infra, CI/CD, scripts). Gemini owns front-side (UI, CSS, motion, canvas/SVG, multimodal, large-context sweeps).

## Gates

### 1. Plan

- **CROSS_VALIDATION trigger (conditional, not default).** Run CV before planning **only** when ANY apply:
  - **Full-stack**: phase straddles back-side AND front-side with unresolved coupling (API contract, shared schema, auth flow).
  - **Unclear**: requirements ambiguous, multiple viable architectures, no obvious side owner.
  - **High-impact**: breaking change, public API, security boundary, data-model migration, irreversible infra, architecture-level decision.

  Otherwise (single-side, clear scope, low blast radius) → skip CV and route directly to the side owner.
- Gather minimum context needed to route. Skip ceremony for trivial tasks.
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
| **Back-side**: backend, API, business logic, database, ORM, system, infra, CI/CD, Docker, scripts, server-side tests, back-end debugging, etc | Codex |
| **Front-side**: UI components, CSS, layout, motion, canvas/SVG, client-side interactions, multimodal input, front-end tests, etc | Gemini |
| Full-stack / unclear / high-impact new work (per CV triggers above) | **Cross-Validation** (Codex + Gemini) → reconcile → assign side owner |
| Single-side new feature with clear scope and low blast radius | Skip CV → assign side owner directly |
| Full-stack phase spanning both sides | Split into back-side + front-side sub-phases; route each |
| Ambiguous side | Ask user |

### 2. Execute

- **Claude-owned (simple):** edit directly with built-in tools.
- **Codex / Gemini:** call `mcp__openmcp__run` with `backend="codex"` (back-side) or `backend="gemini"`. Send: task summary, files, `Done When`, minimum hydrated context (no full files, no pre-written implementation). Default `debug=False` — worker appends its EXTERNAL RESPONSE to `phase-<NN>/journal.md`, no need to inflate the MCP reply.
- **Cross-Validation:** ask Codex and Gemini same narrow question, compare answers, pick direction, route implementation to side owner. **CV dispatches MUST pass `reasoning="high"`** and `debug=True` to `mcp__openmcp__run`.
- Worker edits files via own write tools. Response must list every changed file under `## FILES MODIFIED`.
- **Same-phase fix:** reuse `SESSION_ID`, send only `FIX:` + delta context.
- **MCP failure** → output `BLOCKED`, ask user. No retry, no executor switch, no Task/Agent fallback without explicit consent.
- **Prompt-to-file by default:** write every dispatch prompt to `docs/plans/<slug>/phase-<NN>/prompt.md` (zero-padded phase id) and pass that path to the worker. Inline-in-MCP-`PROMPT` allowed only for one- or two-sentence asks with no context block.
- **Always pass ABSOLUTE paths to MCP workers.** pass `cd` to `mcp__openmcp__run` as an absolute path. This rule applies to every file path mentioned inside the dispatch prompt body as well — input file lists, output targets, decision-note paths, response paths.

**Per-task git commits (required for Codex / Gemini phases):**

- Worker commits its own changes per task — one commit per task in the phase, message prefix `phase-<N>.task-<M>: <summary>`.
- Worker returns commit hashes in `## COMMITS`. Claude does not commit on the worker's behalf.
- Claude reviews diff via `git show <hash>` per task during the Review gate.
- **After Review PASS**, Claude squashes all phase task commits into one: `git reset --soft HEAD~<count> && git commit -m "phase-<N>: <summary>"`. Task-level commits are review artifacts only — not preserved in final history.
- Claude-owned simple edits: commit per logical change, no enforced format.

**Per-phase decision notes (required for Codex / Gemini phases):**

Worker writes one file per phase: `docs/plans/<slug>/phase-<NN>/notes.md`. Append a `## Task <M>` block after finishing each task — do not batch-write at phase end. Each task block captures anything outside the spec:

```markdown
# Phase <N> — Decision Notes

## Task 1
### Decisions made (not in spec)
- <decision>: <why>

### Spec deviations
- <what changed vs phase journal>: <why>

### Tradeoffs accepted
- <tradeoff>: <alternative rejected + reason>

### Assumptions
- <assumption>

### Follow-ups for human
- <thing the human should know>

## Task 2
...
```

Empty sections written as `- none`. Every task gets its own `## Task <M>` block even when all sections are `none` (proves worker considered each).

**Phase journal (required for Codex / Gemini phases):**

`docs/plans/<slug>/phase-<NN>/journal.md` is the single durable phase record. Claude creates it at phase start with the Route skeleton; worker appends the full `# EXTERNAL RESPONSE` block to it (in addition to returning the block inline) before emitting the completion line. Survives session compaction. Replaces the old top-level `PHASE-<N>.md` and `responses/phase-<N>.md` — those are gone.

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
- phase-<NN>/notes.md  (## Task <M>, ## Task <M+1>, …)

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
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
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

Plans spanning multiple Claude sessions persist two files alongside plan doc. Resume artifacts opt-in per plan; flat single-file plans need none.

### `.handover.md` — terse resume pointer

Claude-authored at end of every turn changing plan state (route set, phase change, BLOCKED, phase done). Hook cannot synthesize. `session_refs` is the single source of truth for cached worker SESSION IDs — write after every MCP call returning a SESSION_ID.

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
- docs/plans/<slug>/phase-<NN>/journal.md

## completed_tasks
- id: phase-<N>.task-<M>
  owner: codex | gemini | claude
  commit: <hash>
  notes: docs/plans/<slug>/phase-<NN>/notes.md#task-<M>
- (one row per task; phase journal lives at phase-<NN>/journal.md)

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
  .handover.md             # session_refs holds cached worker SESSION IDs
  phase-01/                # created lazily when Phase 1 starts; no .gitkeep
    prompt.md              # dispatch prompt
    notes.md               # decision notes, ## Task M sub-headers
    journal.md             # phase journal + appended EXTERNAL RESPONSE
  phase-02/
    ...
```

- Phase IDs are zero-padded two digits (`phase-01`, `phase-02`, …).
- Phase folders are created lazily by the executor — never pre-scaffolded.
- Everything inside is committed once the phase finishes — durable audit trail.

### `phase-<NN>/journal.md` — durable phase journal

Created by Claude at phase start with Route skeleton. Worker appends the `# EXTERNAL RESPONSE` block before completion. Claude finalizes Review section after Review gate. Single file per phase — replaces the old top-level `PHASE-<N>.md` plus `responses/phase-<N>.md`.

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

## External Response
<worker appends the full `# EXTERNAL RESPONSE` block here at phase end>

## Review
- Spec Status: ...
- Quality Findings: ...
- Final Status: ...

## Squash Commit
- `<type>[optional scope]: <description>\n\n[optional body]\n\n[optional footer(s)]` # final history after Review PASS

## Decisions
- See `notes.md` (sibling file) for per-task decisions. Cross-task or phase-level decisions noted here only.

## Handoff
<what next phase or new session must do>
```

### Resume rule

New session reads `.handover.md` first, then only the `journal.md` listed in `read_first`. Never scans every phase folder unless handover missing or corrupt.

## Hard Rules

- One phase, one primary owner, one review.
- No draft-then-reimplement handoffs — worker output is final edit.
- Cross-Validation runs **only** when the work is full-stack, unclear, or high-impact (see CV trigger list in Plan gate). Skip for clear single-side work — CV is for catching misses via dual review, not a default ceremony.
- Route by side (back vs front), not default — never auto-route to one executor.
- One commit per task by the worker; missing commit hashes in `## COMMITS` block Review. Task commits are review artifacts only.
- After Review PASS, Claude squashes all phase task commits into one `<type>[optional scope]: <description>\n\n[optional body]\n\n[optional footer(s)]` commit. Final history = one squash commit per phase.
- Per-phase `notes.md` (with `## Task <M>` block per task) + appended EXTERNAL RESPONSE in `journal.md` written before worker emits the final completion line.
- Dispatch prompts written to `phase-<NN>/prompt.md` by default; inline only for trivial one-liner asks.
- User overrides ("use Codex" / "use Gemini" / "no external models" / "skip cross-validation") win.