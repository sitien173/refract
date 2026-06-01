# Shared Agent Contract (`.agents/shared/`) — Design

## Problem

The coordinator↔worker contract — the `# EXTERNAL RESPONSE` block, the completion
line, the per-task commit/notes/journal workflow, and the discipline rules
(test-first, root-cause-first, evidence) — is declared "canonical in
`coordinating-multi-model-work`," and `implementer-prompt.md` tells workers to
"follow that spec." But **Codex/Gemini workers cannot read that spec**:

- Workers are dispatched via `mcp__openmcp__run` with `cd` = the consuming
  project root; they have no knowledge of the plugin's cache install path.
- `.mcp.json` sets `OPENMCP_AGY_DISABLE_PLUGIN` / `OPENMCP_CODEX_DISABLE_PLUGIN`
  / `OPENMCP_GEMINI_ROUTE_TO_AGY` so workers deliberately run **without** the
  superpowers-ccg plugin loaded.

Today the contract is therefore partially re-embedded into every per-phase
`prompt.md` — duplicated, drift-prone, and token-heavy. Prior art
(`2026-04-17-tiered-prompt-architecture-design.md`, "ERP v1.1", Tier-1/Tier-2)
proposed giving workers the protocol once but was never made durable.

## Goal

A project-local, stable-path **canonical contract both the coordinator and the
workers read**: `<project-root>/.agents/shared/`. Dispatch prompts shrink to
pointers; the contract has one source of truth.

## Confirmed Decisions

1. **Scope:** extract two files — `erp.md` (response protocol) and
   `worker-contract.md` (per-task workflow + discipline rules).
2. **Sync:** lazy materialize + version stamp — copy into the project only when
   missing or when the stamp differs from the bundled template.
3. **Git:** the materialized `.agents/shared/` files are git-tracked in the
   consuming project (resume-durable, readable by a fresh session/worker).
4. **Mechanism:** the plugin's `SessionStart` hook performs the deterministic,
   version-stamped copy (no LLM transcription drift; the hook knows its own
   plugin path natively).

## Architecture

```
PLUGIN (cache, version-pinned)            CONSUMING PROJECT (cd for workers)
shared/                                   .agents/shared/        (git-tracked)
  erp.md              <!-- v5.1.0 -->  →    erp.md               <!-- v5.1.0 -->
  worker-contract.md  <!-- v5.1.0 -->  →    worker-contract.md   <!-- v5.1.0 -->
hooks/session-start.sh  ── copies if missing/stale ──┘
skills/coordinating-multi-model-work/SKILL.md  ── points workers at .agents/shared/
skills/executing-plans/implementer-prompt.md   ── thin pointers, phase content only
```

- **Source of truth:** bundled `shared/*.md` in the plugin. Each file's first
  line carries `<!-- ccg-shared-version: X.Y.Z -->` matching the plugin version.
- **Materialized copy:** `<project-root>/.agents/shared/*.md`, byte-identical to
  the bundled templates, committed by the user's project.
- **Resolution:** the hook resolves its own dir via `${BASH_SOURCE[0]}` →
  `PLUGIN_ROOT/shared/`; the project root is the hook's cwd (`$PWD`), same basis
  the existing resume logic already uses for `docs/plans/*/.handover.md`.

## Components

### 1. `shared/erp.md` (new, bundled)
The External Response Protocol, lifted verbatim from
`coordinating-multi-model-work`:
- The `# EXTERNAL RESPONSE` block schema (META, SUMMARY, FILES MODIFIED, COMMITS,
  NOTES, SPEC COMPLIANCE, CLARIFICATIONS NEEDED, NEXT).
- The single completion line: `Phase <N> completed. Journal: …`.
- One line per section explaining what the coordinator scans for.

### 2. `shared/worker-contract.md` (new, bundled)
The worker-facing execution contract:
- Per-task workflow: implement (test-first where applicable) → one commit per
  task `phase-<N>.task-<M>: …` → append `## Task <M>` to `notes.md` (incl. Test
  evidence RED→GREEN / root cause) → append commit row.
- After all tasks: append the `# EXTERNAL RESPONSE` block to `journal.md`.
- Discipline (worker-facing summaries): test-first (no production code without a
  failing test), root-cause-first for bugs, evidence before "done".
- Prompt discipline: edit files on disk, no content duplication, no redesign,
  unclear → CLARIFICATIONS NEEDED + stop.

### 3. `hooks/session-start.sh` (extend)
Add a materialization step that runs **before** the existing JSON output and
writes **nothing to stdout** (stdout is reserved for the hook JSON contract):
- `PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`.
- For each `${PLUGIN_ROOT}/shared/*.md`: target = `${PWD}/.agents/shared/<name>`.
  Copy if target missing OR its `ccg-shared-version` differs from the template's.
- Create `.agents/shared/` as needed. Guard everything with `|| true` so a copy
  failure never suppresses the resume context. Skip silently if
  `${PLUGIN_ROOT}/shared/` is absent (older installs).

### 4. `skills/executing-plans/implementer-prompt.md` (edit)
Replace the embedded `## Response Format`, `## Per-Task Workflow`, and discipline
rules with pointers:
- `## Rules`: "Follow the contract in `<ABS>/.agents/shared/worker-contract.md`."
- `## Response Format`: "Respond per `<ABS>/.agents/shared/erp.md`, then emit the
  completion line."
- Keep phase-specific sections (Original Request, Phase, Tasks, Context, Files,
  Done When). The `cd`-block already passes absolute paths; add the two
  `.agents/shared/...` absolute paths to the dispatch header.

### 5. `skills/coordinating-multi-model-work/SKILL.md` (edit)
Add a short **Shared Contract** subsection under Gate 2 — Execute:
- The worker-facing contract lives in `<project>/.agents/shared/{erp.md,
  worker-contract.md}`, materialized by the SessionStart hook from the plugin's
  bundled `shared/` templates, git-tracked, regenerated on version change.
- Dispatch prompts reference those absolute paths instead of restating the
  protocol. The skill remains the human-readable canonical text; `shared/*.md`
  is the machine-/worker-facing mirror.

## Data Flow (a dispatch)

1. Session starts → hook copies `shared/*.md` → `.agents/shared/*.md` if
   missing/stale.
2. Coordinator routes a phase, writes `phase-<NN>/prompt.md` (phase content only).
3. Dispatch `PROMPT` points the worker to `prompt.md` **and** the two
   `.agents/shared/` files (absolute paths).
4. Worker reads the contract from `.agents/shared/`, executes, commits per task,
   appends notes/journal, returns the `# EXTERNAL RESPONSE` block + completion
   line exactly as `erp.md` specifies.
5. Coordinator reviews against the same canonical contract.

## Sync & Edge Cases

- **Version bump:** plugin update changes the stamp → next session's hook
  overwrites the project copy. Document that `.agents/shared/*.md` are
  generated; edit the plugin's `shared/` templates, not the copies.
- **Hand-edited copy:** overwritten on the next version bump (acceptable —
  plugin-managed). A same-version local edit is preserved (stamp matches).
- **Hook stdout safety:** materialization must not print to stdout; only the
  final JSON block does. `set -euo pipefail` already on → wrap copy in `|| true`.
- **Non-git project / no docs/plans:** unaffected; the copy is independent of the
  resume logic.

## Non-Goals

- No change to routing, the Review gate semantics, or openmcp.
- No Tier-2 "delta follow-up" protocol redesign (separate future work).
- `.agents/shared/` is not auto-added to `.gitignore`; it is meant to be tracked.

## Verification

- **Version-stamp round-trip:** missing → materialized; stale stamp → refreshed;
  matching stamp → untouched; bundled `shared/` absent → no-op.
- **Hook JSON intact:** stdout still parses as the SessionStart JSON contract
  with the materialization step added.
- **Content parity:** `shared/erp.md` matches the `# EXTERNAL RESPONSE` text in
  `coordinating-multi-model-work`; `worker-contract.md` matches the per-task
  workflow + discipline rules.
- **Pointer integrity:** `implementer-prompt.md` no longer restates the protocol
  and references the two `.agents/shared/` paths.

## Execution Note (for the plan)

- Markdown contracts + skill/prompt edits + docs → **coordinator** (docs).
- `hooks/session-start.sh` materialization (shell/infra) → **Codex** (back-side),
  with a coordinator Review of the hook diff and a stdout-safety check.
- Version bump if the contract ships as a feature.
