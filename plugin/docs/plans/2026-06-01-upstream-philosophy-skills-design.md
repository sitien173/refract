# Upstream-Philosophy Skills Alignment — Design

## Goal

Bring Superpowers-CCG's skill set into alignment with the `obra/superpowers`
upstream philosophy, adapted to CCG's multi-model coordinator model:

1. **Test-Driven Development** — write the test first, watch it fail, then code.
2. **Systematic over ad-hoc** — root-cause investigation before any fix.
3. **Complexity reduction** — minimal code, YAGNI, simplest thing that passes.
4. **Evidence over claims** — no completion claim without fresh verification output.

## Gap Analysis

| Pillar | Upstream skill | CCG today |
|---|---|---|
| TDD | `test-driven-development` (Iron Law) | **missing** |
| Systematic | `systematic-debugging` (Iron Law) | **missing** |
| Evidence | `verification-before-completion` (Iron Law + gate + tables) | `verifying-before-completion` — light, no Iron Law/tables |
| Complexity | woven through TDD/writing-skills | only in global CLAUDE.md |

## Confirmed Decisions

- **Scope:** the 3 core philosophy skills only — add `test-driven-development`
  and `systematic-debugging`; strengthen `verifying-before-completion`.
  (No code-review, worktrees, subagent, or writing-skills ports this round.)
- **Style:** CCG-native — concise `SKILL.md` matching the house contract
  (`Use When` / `Workflow` / `Hard Rules` / `References`), but discipline skills
  keep their teeth: Iron Law near the top, a compact Red Flags list, and a short
  Rationalizations table. Whoever writes production code follows the discipline
  (coordinator for trivial edits; Codex/Gemini workers otherwise); the
  coordinator enforces it at the Review gate.
- **Integration:** wire the three disciplines into the workflow so they are
  *enforced*, not just documented — Review gate + Execute gate of
  `coordinating-multi-model-work`, plus the `executing-plans/implementer-prompt.md`
  dispatch template.

## Skill Content Contract (per house style)

Each new/updated `SKILL.md`:

- Frontmatter: `name` (lowercase-hyphen), `description` (third person, starts
  "Use when…", triggering conditions only — no workflow summary).
- Iron Law stated once, near the top (discipline skills).
- `## Use When`, `## Workflow`, `## Hard Rules`, `## References`.
- Compact `## Red Flags` + `## Rationalizations` table for discipline skills.
- CCG routing note: who executes (coordinator vs side worker) and where the
  coordinator enforces (Review gate). References point one level deep to
  `coordinating-multi-model-work` and sibling skills — no nested chains.

## Per-Skill Substance

### `test-driven-development`
- Iron Law: **No production code without a failing test first.**
- Red → verify-it-fails → Green (minimal) → verify-it-passes → Refactor.
- CCG framing: dispatched workers write the failing test as task-1 of any
  feature/bugfix; the failing-then-passing evidence appears in the worker's
  `## NOTES` / journal; coordinator rejects a phase whose `## COMMITS` show
  production code with no preceding/accompanying test evidence.
- Complexity reduction lives here (minimal GREEN code, YAGNI).

### `systematic-debugging`
- Iron Law: **No fixes without root-cause investigation first.**
- Four phases: Root Cause → Pattern Analysis → Hypothesis & Test → Fix.
- 3+ failed fixes ⇒ question the architecture, stop, ask the user.
- CCG framing: route the bug by side (back → Codex, front → Gemini); the
  dispatch prompt requires a stated root-cause hypothesis with evidence before
  a fix commit; Phase 4 fix begins with a failing test (links TDD); coordinator
  requires that evidence at Review.

### `verifying-before-completion` (strengthen)
- Iron Law: **No completion claims without fresh verification evidence.**
- Gate function: identify command → run full → read output/exit code → verify →
  only then claim. Add Red Flags and Rationalizations tables.
- Keep the existing CCG Review-gate hand-off (Spec status + Quality scan).

## Integration Points

- `coordinating-multi-model-work/SKILL.md`
  - **Execute gate:** for feature/bugfix phases, workers follow TDD; debugging
    phases follow systematic-debugging.
  - **Review gate:** add an explicit discipline check — test-first evidence,
    root-cause evidence (for fixes), fresh verification output — and reference
    the three skills.
- `executing-plans/implementer-prompt.md`
  - `## Rules`: feature/bugfix work is test-first; bug fixes start from a failing
    test reproducing the bug.
  - `## Per-Task Workflow`: capture the RED (failing) then GREEN (passing) result.
  - `## Done When`: include the verification command whose fresh output is the
    evidence.
- `CLAUDE.md` + `README.md`: list the three skills.

## Non-Goals

- No automated test harness is added (none exists; `docs/testing.md` documents the
  headless-session methodology). Verification this round is structural review of
  changed files (frontmatter, one-level references, resolvable cross-references,
  line budget) per the Review gate.
- No behavior change to routing, resume artifacts, or the openmcp server.

## Verification

Structural review scoped to changed files:
- Frontmatter: `name` lowercase-hyphen, `description` third-person "Use when…".
- References resolve and stay one level deep.
- Cross-references (skill names) match real skill directories.
- `SKILL.md` line budget respected; no orphaned links.
