# Implementation Plan — Smart Routing Optimization

Date: 2026-05-07
Source design: `docs/plans/2026-05-07-routing-optimization-design.md`
Owner: claude (orchestrator)

## Files In Scope

- `skills/coordinating-multi-model-work/routing-decision.md`
- `skills/coordinating-multi-model-work/checkpoints.md`
- `skills/shared/protocol-threshold.md`
- `skills/shared/multi-model-integration-section.md`
- `superpowers-ccg.md`
- `rules/ccg-workflow.mdc`
- `hooks/user-prompt-submit.sh`
- `tests/claude-code/test-cp1-routing-guards.sh`
- `CLAUDE.md` (root)

## Phase 1: Update canonical routing matrix + add new axes

**Owner:** `codex`

**Goal:** Replace Detailed + Compact matrices in routing-decision.md with revised matrix; add Tiebreakers and New Axes sections; refresh Session Policy table.

**Files:**
- Modify: `skills/coordinating-multi-model-work/routing-decision.md`

**Tasks:**
1. Replace "Detailed Task Matrix" with revised rows (multimodal, large-context, horizon, security review-gate, visual regression, doc/spec extraction).
2. Replace "Compact Routing Matrix" to mirror revised rows.
3. Add "New Routing Axes" section (context size >200K, multimodal input, horizon length).
4. Add "Tiebreaker Order" section (5-step priority).
5. Update Session Policy table (add multimodal artifact carryover, long-horizon Codex active row).
6. Update "Decision Guidelines" + "Example" so they stay consistent.

**Acceptance Criteria:**
- Both matrices contain all rows from design doc.
- Tiebreaker section ordered 1-5 exactly as design.
- Claude never appears as executor for non-trivial code paths.
- Security row notes mandatory Claude review gate.

**Reviewer Checklist:**
- All design-doc rows present, no extras.
- Tiebreaker order matches design.
- Session policy adds 2 new rows without breaking existing.
- No drift from design doc terminology (Codex, Gemini, Claude).

**Integration Checks:**
- `bash tests/claude-code/run-skill-tests.sh --test test-cp1-routing-guards.sh`

## Phase 2: Sync downstream references

**Owner:** `codex`

**Goal:** Propagate new matrix/triggers/tiebreakers to all repo locations that duplicate or summarize routing rules.

**Files:**
- Modify: `superpowers-ccg.md`
- Modify: `rules/ccg-workflow.mdc`
- Modify: `CLAUDE.md`
- Modify: `skills/coordinating-multi-model-work/checkpoints.md`
- Modify: `skills/shared/protocol-threshold.md`
- Modify: `skills/shared/multi-model-integration-section.md`
- Modify: `hooks/user-prompt-submit.sh` (CP1 routing guide block embedded in hook output)

**Tasks:**
1. Update each file's routing matrix or trigger table to mirror Phase 1 canonical version.
2. Add tiebreaker ordering reference (link or short inline copy) where matrix is summarized.
3. Update hook script's heredoc CP1 table to revised matrix; preserve tier budgets and failure rules.
4. Search for stale phrases ("UI dominates the phase" as sole Gemini trigger) and replace with broader Gemini triggers.

**Acceptance Criteria:**
- `grep -r "UI dominates"` returns only contextually correct usages.
- All embedded routing tables identical row set across files.
- Hook script still emits valid CP1 reminder block.

**Reviewer Checklist:**
- No file lags Phase 1 matrix.
- Tiebreaker order present at each summary location.
- Hook heredoc syntax intact (no broken quoting).
- CLAUDE.md trigger table updated.

**Integration Checks:**
- `bash hooks/user-prompt-submit.sh < /dev/null | head -80` (ensure no syntax error)
- `bash tests/claude-code/run-skill-tests.sh --test test-cp1-routing-guards.sh`

## Phase 3: Update routing-guards test for new matrix

**Owner:** `codex`

**Goal:** Adjust `test-cp1-routing-guards.sh` so it asserts new triggers (multimodal, >200K, horizon) and tiebreaker fallback to Codex.

**Files:**
- Modify: `tests/claude-code/test-cp1-routing-guards.sh`

**Tasks:**
1. Add fixture prompts for: screenshot→code (expect Gemini), >200K context sweep (expect Gemini), 7-hr refactor (expect Codex), security CRUD (expect Codex + review-gate note).
2. Assert tiebreaker behavior: multimodal+UI → Gemini; security+multimodal → Codex (rule 1 wins).
3. Keep existing pass cases; remove obsolete "UI dominates" assertion if it conflicts.

**Acceptance Criteria:**
- New cases pass.
- Existing valid cases still pass.
- Tiebreaker priority assertions present.

**Reviewer Checklist:**
- Test fixtures map 1:1 with new matrix rows.
- No false positives on Claude-as-executor.

**Integration Checks:**
- `bash tests/claude-code/run-skill-tests.sh --test test-cp1-routing-guards.sh`
- `bash tests/claude-code/run-skill-tests.sh` (full suite, no regressions)

## Phase 4: Final review + commit

**Owner:** `claude`

**Goal:** Verify cross-file consistency and produce a single commit.

**Tasks:**
1. Diff-review every modified file against design doc.
2. Stage + commit (rtk git add/commit) with conventional commit message.

**Acceptance Criteria:**
- Commit message references design doc path.

**Reviewer Checklist:**
- No file drifted from canonical matrix.
- No leftover TODOs.
- No accidental matrix duplication left in deprecated form.

## Risk Notes

- Hook script embeds CP1 table inside heredoc — quoting breakage risks BLOCKED on next prompt. Phase 2 must validate hook executes.
- Cross-file matrix drift is highest regression risk; Phase 4 diff-review mitigates.
