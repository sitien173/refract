---
name: coordinating-multi-model-work
description: "Three-gate workflow (Plan → Execute → Review)"
---

# Coordinating Multi-Model Work

Claude plans, routes, reviews, integrates, and handles simple tasks directly. Codex owns back-side (backend, API, business logic, database, ORM, system, infra, CI/CD, Docker, scripts, server-side tests/debug). Gemini owns front-side (UI, CSS, layout, motion, canvas/SVG, client interactions, multimodal, front-end tests, large-context sweeps).

**Cross-Validation (CV)** = ask Codex and Gemini the same narrow question, reconcile divergences, then route implementation to a side owner. Run CV **only** when a phase is:
- **Full-stack** — straddles both sides with unresolved coupling (API contract, shared schema, auth flow), or
- **Unclear** — ambiguous requirements, multiple viable architectures, no obvious owner, or
- **High-impact** — breaking change, public API, security boundary, data migration, irreversible infra, architecture decision.

Otherwise route directly to the side owner. CV dispatches MUST pass `reasoning="high"`.

## Gate 1 — Plan

Gather the minimum context to route (skip ceremony for trivial work). Frame work as one phase: 2–4 related tasks, file set, `Done When` checks. Decide owner by **side**, then output:

```text
# ROUTE
- Owner: Claude | Codex | Gemini | Cross-Validation
- Reason: [one line — back-side / front-side / simple / new-feature ideation]
- Done When: [build/test/lint commands or acceptance bullets]
```

| Phase | Owner |
|---|---|
| Simple/trivial (one-line edit, rename, doc tweak, single-file fix, clarification) | Claude |
| Back-side work | Codex |
| Front-side work | Gemini |
| Full-stack / unclear / high-impact (per CV triggers) | Cross-Validation → reconcile → side owner |
| Single-side, clear scope, low blast radius | Skip CV → side owner directly |
| Full-stack phase spanning both sides | Split into back/front sub-phases; route each |
| Ambiguous side | Ask user |

## Gate 2 — Execute

- **Claude (simple):** edit directly; commit per logical change.
- **Codex / Gemini:** call `mcp__openmcp__run` with `backend="codex"` (back) or `"gemini"`/`"agy"` (front). The worker edits files with its own write tools — on-disk files are the source of truth, never a draft. Reuse cached `SESSION_ID` when present.
- **Cross-Validation:** same narrow question to both, compare, pick direction, route to the side owner (`reasoning="high"`).
- **Same-phase fix:** reuse `SESSION_ID`; send only `FIX:` + delta context.
- **MCP failure / rejected SESSION_ID** → output `BLOCKED`, ask the user. No retry, executor switch, or Task/Agent fallback without explicit consent.

**Paths:** always pass ABSOLUTE paths (forward slashes on Windows) to MCP workers — the `cd` arg, the `PROMPT` pointer, and every path inside the prompt body. Gemini/agy mis-resolves relative paths.

**Dispatch prompt:** write it to `docs/plans/<slug>/phase-<NN>/prompt.md` (template in `implementer-prompt.md`) and pass its absolute path. Inline `PROMPT` only for one- or two-sentence asks with no context block.

**Per-task commits (Codex / Gemini phases):** the worker makes one commit per task, subject `phase-<N>.task-<M>: <summary>`, and returns hashes in `## COMMITS`. Claude never commits on the worker's behalf and reviews each via `git show <hash>`. After Review PASS, Claude squashes the phase into one commit: `git reset --soft HEAD~<count> && git commit -m "phase-<N>: <summary>"` — task commits are review artifacts only.

**Per-phase notes (Codex / Gemini phases):** the worker appends a `## Task <M>` block to `docs/plans/<slug>/phase-<NN>/notes.md` after each task (not batched at phase end). Each block has: Decisions made (not in spec), Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human. Empty sub-sections = `- none`; every task gets a block even if all `none`.

**Phase journal (Codex / Gemini phases):** `docs/plans/<slug>/phase-<NN>/journal.md` is the single durable phase record (survives compaction). Claude creates it at phase start with the Route skeleton; the worker appends its full `# EXTERNAL RESPONSE` block before emitting the completion line.

### Worker response format

```text
# EXTERNAL RESPONSE
## META
- Phase / Owner (codex|gemini) / SessionID / Started / Finished / Plan dir
## SUMMARY
[one sentence]
## FILES MODIFIED
| Action | Path | Change |
## COMMITS
- phase-<N>.task-<M>: <hash>  <subject>
## NOTES
- phase-<NN>/notes.md  (## Task <M>, …)
## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO  — [one line]
## CLARIFICATIONS NEEDED
None (or list questions; emit and stop if any)
## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE
```

Then the single completion line Claude scans for:

```text
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
```

## Gate 3 — Review

**(a) Spec & Integration** — run the phase's `Done When` checks; compare result vs request, file scope, integration output. Initial status: `PASS` | `PASS_WITH_DEBT` | `FAIL`.

**(b) Quality scan** — scan every file in `## FILES MODIFIED` (stay scoped to changed files — no broader audit):

| Category | Check |
|---|---|
| Edge cases | null/undefined, empty arrays, boundaries, off-by-one |
| Error handling | swallowed errors, missing catch, unhandled rejections |
| Security | injection (SQL/XSS/cmd), hardcoded secrets, unsafe deserialization, missing boundary validation |
| Naming & clarity | misleading names, ambiguous abbreviations, scope creep vs name |
| Duplication | copy-paste logic that should be extracted |
| Correctness | logic errors, race conditions, resource leaks, bad type narrowing |

| Severity | Effect |
|---|---|
| CRITICAL — bug, security vuln, data-loss | Force `FAIL` |
| HIGH — likely bug / significant gap | Force `FAIL` |
| MEDIUM — code smell, missed edge case | `PASS` → `PASS_WITH_DEBT` |
| LOW — minor naming/style | Noted only |

Skip the Quality scan only when: docs/coordination-only phase, Claude one-line/trivial edit, or `## FILES MODIFIED` empty. Required for every Codex / Gemini phase. Discard findings that contradict the user's explicit request or project conventions (with explanation).

```text
# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Quality Findings:
  | Severity | path:line | Problem | Fix |
  (or "No findings" / "Skipped: <reason>")
- Final Status: PASS | PASS_WITH_DEBT | FAIL
- Explanation: [one line — what changed from spec status and why]
- Next: [done | debt + owner | retry/clarify]
```

`PASS_WITH_DEBT` requires an explicit non-blocking debt note. `FAIL` blocks completion — re-route the gap or ask the user. Reject the phase if `## COMMITS` hashes, `notes.md` task blocks, or the journal External Response section are missing.

### Cross-Validation output

```text
# CROSS-VALIDATION
- Agreement: [shared conclusions]
- Divergences: [one line per disagreement + chosen resolution]
- Next owner: Codex | Gemini | Claude
```

## Session-Resume Artifacts

Opt-in per plan; flat single-file plans need none. Multi-phase / multi-session plans persist `.handover.md` + per-phase `journal.md` alongside `PLAN.md`.

**Plan directory layout** (phase IDs zero-padded to two digits; phase folders created lazily by the executor, never pre-scaffolded):

```
docs/plans/<slug>/
  PLAN.md
  .handover.md
  phase-01/
    prompt.md   # dispatch prompt
    notes.md    # per-task decision notes
    journal.md  # Route skeleton + appended EXTERNAL RESPONSE + Review
```

**`.handover.md`** — terse resume pointer, always Claude-authored (a hook cannot synthesize it). Rewrite at the end of every turn that changes plan state (route set, phase change, BLOCKED, phase done). `session_refs` is the single source of truth for cached worker SESSION IDs — update it after every MCP call that returns one.

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
- id / owner / commit / notes  (one row per finished task)
## blockers
<empty | one line per blocker>
## decisions_delta
<empty | new decisions since prior handover>
## uncommitted_files
<empty | edited-but-not-committed paths>
```

**`phase-<NN>/journal.md`** — durable per-phase record. Claude writes the skeleton at phase start; the worker appends its `# EXTERNAL RESPONSE`; Claude finalizes the Review after the gate.

```markdown
# Phase <N> — <title>
- Status / Owner / Started / Finished
## Route
- Reason / Done When / Files
## External Response
<worker appends the full # EXTERNAL RESPONSE block>
## Review
- Spec Status / Quality Findings / Final Status
## Squash Commit
- <type>[scope]: <description>   # final history after Review PASS
## Decisions
- per-task decisions live in notes.md; cross-task / phase-level noted here
## Handoff
<what the next phase or session must do>
```

**Resume rule:** a new session reads `.handover.md` first, then only the `journal.md` files listed in `read_first`. Never scan every phase folder unless the handover is missing or corrupt.

## Hard Rules

- One phase, one owner, one review. Worker output is the final edit — no draft-then-reimplement.
- Route by side; never auto-route to one executor. CV only for full-stack / unclear / high-impact work.
- One commit per task by the worker; missing `## COMMITS` hashes, `notes.md` task blocks, or journal External Response block Review.
- Notes + journal External Response written before the worker's completion line.
- Absolute paths only when talking to MCP workers.
- User overrides ("use Codex/Gemini", "no external models", "skip cross-validation") always win.
