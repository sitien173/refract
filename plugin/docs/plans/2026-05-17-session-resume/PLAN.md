# Session-Resume System — Plan

Date: 2026-05-17
Owner: Claude (orchestrator), Codex (hook script)

## Problem

When a Claude Code session ends mid-plan, the orchestrator loses:
1. Codex/Gemini `SESSION_ID`s — workers restart cold next session.
2. Phase progress, route decisions, blockers — orchestrator restarts cold next session.

Result: re-explaining everything to workers and to itself burns context budget on
already-decided work.

## Design (Cross-Val reconciled)

Three new artifacts per plan, plus one hook:

| Artifact | Purpose | Writer | Lifetime |
|---|---|---|---|
| `.sessions.json` | Worker `SESSION_ID` cache | Orchestrator after each MCP call | Until MCP rejects, plan-scoped |
| `.handover.md` | Terse resume pointer (≤500 tok) | Orchestrator end-of-turn on state change | Until plan done |
| `PHASE-<N>.md` | Durable phase journal | Orchestrator after Review gate | Permanent |
| `hooks/session-start.sh` | Auto-inject handover on session start | Shell script | n/a |

Plan folder layout (new for plans that ship resume artifacts):

```
docs/plans/<YYYY-MM-DD-slug>/
  PLAN.md            # spec (this file's equivalent)
  PHASE-1.md         # finalized journal entries
  PHASE-2.md
  .handover.md       # terse resume pointer
  .sessions.json     # worker session IDs (gitignored)
```

Legacy flat-file plans (`docs/plans/<date>-<slug>-plan.md`) still supported;
resume artifacts only required for plans that opt in.

## Schemas

### `.sessions.json`

```json
{
  "schema_version": 1,
  "plan_path": "docs/plans/2026-05-17-session-resume",
  "current_phase": 2,
  "phase_owner": "codex",
  "sessions": {
    "codex":  "019e35bf-...",
    "gemini": "ef339a97-..."
  },
  "last_updated": "2026-05-17T10:12:44Z"
}
```

Lifecycle:
- Read on plan load + before each MCP call.
- Write after every MCP call that returns a SESSION_ID.
- Cache miss (id absent) → fresh session allowed.
- Cache present but rejected by MCP → `BLOCKED`. User clears entry manually (`rm` the file or edit the offending id), then retries.
- No TTL. Worker server-side expiry is unknown — guessing throws away warm context. Let MCP be source of truth; user intervenes on rejection.

### `.handover.md`

Frontmatter + body. ≤500 tokens total.

```markdown
---
plan: docs/plans/2026-05-17-session-resume
updated_at: 2026-05-17T10:12:44Z
current_phase: 2
status: ACTIVE   # ACTIVE | BLOCKED | DONE
owner: codex
session_refs:
  codex: 019e35bf-...
  gemini: ef339a97-...
---

## next_action
[one to three sentences — exact next step]

## read_first
- docs/plans/2026-05-17-session-resume/PHASE-2.md

## blockers
[empty | one line per blocker]

## decisions_delta
[empty | new decisions since prior handover]

## uncommitted_files
[empty | paths of edited-but-unreviewed files]
```

Writer: orchestrator (Claude) writes via `Write` tool at end of every turn that
changes plan state (route set, phase change, BLOCKED, phase done). Stop hook
cannot synthesize this — must be Claude-authored before Stop fires.

### `PHASE-<N>.md`

Created at phase start with Route skeleton. Finalized immediately after Review.

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
[what next phase or new session must do]
```

Resume rule: new session reads `.handover.md` first, then only files in
`read_first`. Never scans every PHASE file unless handover is missing/corrupt.

### Hook: `hooks/session-start.sh`

Extend existing hook. After current static workflow injection, walk
`docs/plans/*/.handover.md` and `docs/plans/*/PLAN.md`:

1. Find newest `.handover.md` with `status: ACTIVE`.
2. Check companion `.sessions.json` exists; report id presence (no TTL check).
3. Append to `additionalContext`:
   ```
   <RESUME>
   Active plan: <plan_path>
   Current phase: <N>
   Owner: <owner>
   Next action: <next_action>
   Read first: <files>
   Sessions: codex=<present|absent>, gemini=<present|absent>
   </RESUME>
   ```
4. If no ACTIVE handover found → emit nothing (preserve current behavior).

Shell-only; no JSON parsing beyond grep/awk. Tolerate missing files.

## Phases

### Phase 1 — Skill docs + gitignore (Claude direct)

Files:
- `skills/coordinating-multi-model-work/SKILL.md` — add **Session-Resume Artifacts** section: `.sessions.json` schema + lifecycle, `.handover.md` schema + when to write, `PHASE-<N>.md` schema + when to write. Reference BLOCKED-on-rejection rule.
- `skills/executing-plans/SKILL.md` — add steps: load handover on start, write/update `.sessions.json` after each MCP call, write `PHASE-<N>.md` after Review, update `.handover.md` at end of every state-changing turn.
- `.gitignore` — add `**/.sessions.json` (worker IDs are local) and keep `**/.handover.md` tracked (resume pointer is durable).

Done When:
- Both SKILL.md files updated.
- `.gitignore` updated.
- Grep for `sessions.json` finds new docs.

### Phase 2 — SessionStart hook extension (Codex)

Files:
- `hooks/session-start.sh` — extend with handover walker per spec above.

Done When:
- `bash hooks/session-start.sh` exits 0 with no active plan present.
- With a mock `docs/plans/test/.handover.md`, output JSON includes `<RESUME>` block.
- Existing static workflow context still injected.

### Phase 3 — Example artifacts + verification (Claude direct)

Files:
- `docs/plans/2026-05-17-session-resume/PLAN.md` — copy of this file moved into folder layout.
- `docs/plans/2026-05-17-session-resume/PHASE-1.md` — populated journal after Phase 1 done.
- `docs/plans/2026-05-17-session-resume/PHASE-2.md` — populated journal after Phase 2 done.
- `docs/plans/2026-05-17-session-resume/.handover.md` — final state.

Done When:
- Folder exists with all four files.
- New Claude session started in repo emits `<RESUME>` block referencing this plan.

## Hard Rules

- Worker SESSION_ID rejection by MCP → `BLOCKED`. No silent retry.
- `.handover.md` always Claude-authored, never hook-synthesized.
- No TTL on session cache. MCP rejection is the only invalidation signal. User clears manually after BLOCKED.
- Resume reading: handover first, then explicit `read_first` only.
