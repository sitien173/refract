# Tiered Prompt Architecture v2 — Critique & Improvement Backlog

**Date:** 2026-04-18
**Reviews:** `docs/plans/2026-04-17-tiered-prompt-architecture-design.md` (the just-shipped 3-tier system)
**Goal:** Document weaknesses, edge cases, and prioritized improvements for the next iteration.

---

## TL;DR

The shipped 3-tier system is **good for the typical case** (3-5 phases, sequential, single user) and **fragile for edge cases** (session expiration, human edits between phases, partial worker output, long Tier-3 chains). The biggest gap is **silent failure modes** — there's no detection when assumptions break.

Single highest-ROI fix: **A1 — session-not-found auto-downgrade to Tier 1**.

---

## Section 1: Critical Weaknesses

### 1.1 No drift detection — Tier 3 is unverified faith in session memory
We picked "sessions are reliable, trust them" but built zero verification. After 5+ phases on the same `SESSION_ID`, the worker may have a compacted/lossy view of phase_01. No probe, no signal when drift starts.

**Fix:** add a one-line context-checksum — Tier 3 prompts include "Recall: you previously {summary}" assertion the worker must implicitly confirm or correct.

### 1.2 The "2 Tier-2 follow-ups max" rule is arbitrary
Why 2? A typo fix takes 1 turn; an architectural misunderstanding won't be fixed in 10. Real metric is *convergence*.

**Fix:** measure delta between consecutive `FIX` prompts. Substantively similar `FIX_n` ≈ `FIX_n-1` → escalate even at retry 1. Shrinking gap → allow 3rd retry.

### 1.3 Tier 2 has only one `FIX` field — partial outputs break the model
If Codex returns 4 correct files and 1 wrong, structured delta can't express "fix file A like X, but file B's API also needs Y."

**Fix:** allow `FIX` to be a list (`FIX:` lines, one per gap) with optional file scoping.

### 1.4 `Done When` conflates worker instructions and reviewer acceptance
Worker reads as guidance; reviewer reads as pass/fail gate. Different precision required.

**Fix:** mark items as `[verify: <command>]` when they're CP4 gates, leave others as guidance.

### 1.5 Cross-Validation × Session-Policy is undefined
If CP1 routes to Cross-Validation (Codex + Gemini), do both use Tier 1? The spec is silent.

**Fix:** mandate Tier 1 + `SESSION_POLICY: FRESH` for both models in cross-validation; Tier 3 is meaningless for comparison perspectives.

---

## Section 2: Risks & Edge Cases

### 2.1 Session expiration mid-workflow
Codex/Gemini sessions aren't infinite. Long Claude review between phases may expire the session. Tier 3 fails silently.

**Fix:** treat session-not-found error as automatic downgrade to Tier 1; mint new SESSION_ID.

### 2.2 Claude orchestrator context compression
Claude's own context window gets compressed. After heavy compression, Claude may forget which `SESSION_ID` belongs to which worker.

**Fix:** persist `SESSION_ID` + phase metadata in `.ccg/sessions.json`.

### 2.3 Files modified by non-CCG actors (human edits, git pulls)
Tier 3 assumes "the worker already knows the file." Manual edits between phases poison this assumption.

**Fix:** before Tier 3, hash explicit file set; force-include any changed file in `New/Changed Files`.

### 2.4 Phase reordering / non-linear execution
Workflow assumes phase_01 → phase_02 → phase_03. User-driven reordering breaks Tier 3 references.

**Fix:** explicitly require `FRESH` when phase order doesn't match plan order.

### 2.5 Worker hallucination of "remembered" context
With Tier 3's tiny prompts, no anchor disproves false memories. Worker confidently references functions never written.

**Fix:** Tier 3 prompts include 1-line ground-truth: "Files you previously created: X, Y. Do not assume others exist."

### 2.6 CP4 FAIL on a Tier-3 phase contaminates the session
Fixing via Tier 2 reuses the now-poisoned session. Mistaken assumptions persist.

**Fix:** any CP4 FAIL on a Tier-3 phase triggers SESSION_POLICY reset on the *next* phase, not at the retry threshold.

### 2.7 Concurrent CCG sessions on the same repo
Two Claude instances mint independent `SESSION_ID`s and race on file edits. No mutex.

**Fix:** out of scope; document as known limitation.

---

## Section 3: Clarity & Scalability

### Clarity strengths
- 3-tier naming is unambiguous in PR/chat references.
- `Done When` reads naturally vs split sections.
- `SESSION_POLICY: CONTINUE | FRESH` is binary and discoverable.

### Clarity weaknesses

**3.1 Three-plus places define the same rules** — `codex-base.md`, `gemini-base.md`, `context-sharing.md`, `protocol-threshold.md`, `INTEGRATION.md`, hooks. **Fix:** make `context-sharing.md` canonical; others reference, not restate.

**3.2 Tier numbering implies escalation ladder** — Tier 3 sounds like an upgrade over Tier 1. They're orthogonal modes. **Fix:** rename to `INITIAL`, `FIX`, `CONTINUE`.

**3.3 Decision logic lives only in prose** — **Fix:** add a flowchart at the top of `context-sharing.md`:
```
Worker call?
├─ First call ever for this phase? → INITIAL (FRESH)
├─ Same phase failed CP4? → FIX
└─ New phase, same worker, related? → CONTINUE
```

### Scalability concerns

**3.4 Linear growth in worker session memory** — Tier 3 chains accumulate without bound. **Fix:** soft cap at 5-7 consecutive Tier-3 phases; force `FRESH` to compact.

**3.5 No per-phase token measurement** — "75% savings" claim is unverifiable. **Fix:** opt-in JSON log `{tier, prompt_tokens, response_tokens, phase_id}`.

**3.6 CP1 routing is judgment-bound** — "Same subsystem?" varies by run. **Fix:** deterministic helper — "if 50%+ of files in new phase overlap with prior phase's file set, default `CONTINUE`."

**3.7 No plan archival** — `docs/plans/` accumulates indefinitely. **Fix:** quarterly archive policy for plans older than 90 days.

---

## Section 4: Prioritized Recommendations

### Tier A — Do soon (high impact, low effort)

**A1. Session-not-found auto-downgrade to Tier 1**
*Risk: silent failure on expired sessions.*
Wrap Tier 2/3 calls so any "session not found / expired" error transparently rebuilds a Tier 1 prompt. ~30 min of doc edits + a small wrapper note in `checkpoints.md`. **Highest ROI.**

**A2. Single source of truth for tier rules**
*Risk: doc drift across 6 files.*
Make `context-sharing.md` canonical; replace duplicated rules elsewhere with one-line references. ~1 hour.

**A3. Add file-hash freshness check to Tier 3**
*Risk: human edits between phases poison continuation.*
Before Tier 3, hash explicit file set; force-include changed files in `New/Changed Files`. ~1 hour.

### Tier B — Do next (medium impact)

- **B1.** Multi-FIX support in Tier 2 (list with optional file scoping)
- **B2.** Replace tier numbers with mode names (`INITIAL` / `FIX` / `CONTINUE`)
- **B3.** 1-line ground-truth anchor in Tier 3 prompts
- **B4.** Soft cap on consecutive Tier-3 phases (5-7 max)

### Tier C — Backlog (high effort or speculative)

- **C1.** Convergence-based retry policy (replaces hard 2-retry cap)
- **C2.** Persistent `.ccg/sessions.json` for orchestrator context survival
- **C3.** Per-phase token telemetry (opt-in JSON log)
- **C4.** Deterministic SESSION_POLICY heuristic (file-overlap %)

### Tier D — Out of scope (acknowledge as known limits)

- Concurrent CCG sessions on the same repo
- Plan archival policy
- Non-English prompt support
- Phase reordering / non-linear execution

---

## Suggested Next Step

Implement **Tier A** items as a single small phase (~3 hours total). Reassess Tier B after observing the system in real use for a week — some "weaknesses" listed here may not actually bite often enough to warrant fixes.
