# Context-Retrieval CP0 Implementation Plan

## Summary

Replace Auggie with the `context-retrieval` MCP suite across active CP0 instructions, docs, hooks, and guard tests. Keep wiki and Grok Search behavior unchanged.

## Source Design

- `docs/plans/2026-05-05-context-retrieval-cp0-design.md`

## Phase 1: Update CP0 guardrail tests

**Owner:** `claude`

**Routing Notes:** Test and coordination change; handle directly unless user requests external execution.

**Goal:** Make CP0 tests define the new context-retrieval contract and reject active Auggie references.

**Files:**
- Modify: `tests/claude-code/test-cp0-context-acquisition-guards.sh`
- Modify: `tests/claude-code/README.md`

**Tasks:**
1. Replace Auggie expectations with context-retrieval + Grok Search expectations.
2. Add assertions for `codebase_retrieve`, `codebase_map`, and `codebase_grep` tool roles.
3. Add active-doc assertion that Auggie is absent from CP0 target files.
4. Update test documentation to describe the context-retrieval CP0 guard.

**Acceptance Criteria:**
- CP0 guard test fails if active CP0 docs mention Auggie.
- CP0 guard test requires all three context-retrieval tool roles.
- Test README no longer describes Auggie as the CP0 local tool.

**Reviewer Checklist:**
- Test targets cover hooks, top-level docs, shared CP0 docs, and coordinating skill docs.
- Historical release notes and old plans are not included in active Auggie rejection.
- Grok Search remains external/current-only in test expectations.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp0-context-acquisition-guards.sh`

## Phase 2: Update active CP0 instructions and shared docs

**Owner:** `claude`

**Routing Notes:** Documentation and hook-instruction change; handle directly unless user requests external execution.

**Goal:** Replace active Auggie CP0 wording with the context-retrieval suite contract.

**Files:**
- Modify: `hooks/session-start.sh`
- Modify: `hooks/user-prompt-submit.sh`
- Modify: `skills/shared/protocol-threshold.md`
- Modify: `skills/shared/supplementary-tools.md`
- Modify: `skills/coordinating-multi-model-work/SKILL.md`
- Modify: `skills/coordinating-multi-model-work/checkpoints.md`
- Modify: `skills/coordinating-multi-model-work/context-sharing.md`

**Tasks:**
1. Replace hook CP0 reminders so local context uses context-retrieval after optional wiki lookup.
2. Document tool selection: retrieve for semantic anchors, map for architecture relationships, grep for exact references.
3. Update shared CP0 matrix and supplementary tool reference.
4. Preserve `HYDRATED_CONTEXT` budget and CP0 artifact normalization rules.

**Acceptance Criteria:**
- Runtime hook text no longer instructs Auggie use.
- Shared docs name context-retrieval as the active local CP0 context contract.
- Wiki lookup and Grok Search rules remain unchanged.
- CP1-CP4 exact block formats remain unchanged.

**Reviewer Checklist:**
- No stale Auggie wording remains in active CP0 files touched by guard tests.
- Tool split is consistent across hooks and docs.
- No fallback to Auggie is introduced.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp0-context-acquisition-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-token-efficiency-guards.sh`

## Phase 3: Update top-level project docs, rules, and release metadata

**Owner:** `claude`

**Routing Notes:** Docs and version coordination; handle directly unless user requests external execution.

**Goal:** Align user-facing docs and project rules with the new CP0 contract, then bump plugin version.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `superpowers-ccg.md`
- Modify: `rules/ccg-workflow.mdc`
- Modify: `rules/global-claude-workflow.mdc`
- Modify: `package.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Tasks:**
1. Replace top-level Auggie wording with context-retrieval wording.
2. Keep model routing and CP checkpoint descriptions unchanged except CP0 local context tool.
3. Bump plugin/package metadata for release visibility.
4. Leave historical release notes and old plans unchanged unless active tests require updates.

**Acceptance Criteria:**
- Active user-facing docs describe context-retrieval CP0 local context.
- Required tools list no longer names Auggie.
- Version metadata is consistently bumped.

**Reviewer Checklist:**
- No unrelated routing, command, or model text changes.
- Version fields are consistent across package and plugin metadata.
- Historical docs are not rewritten unnecessarily.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp0-context-acquisition-guards.sh`
- `rtk grep -R "Auggie\|auggie" hooks README.md superpowers-ccg.md CLAUDE.md rules skills tests/claude-code/README.md tests/claude-code/test-cp0-context-acquisition-guards.sh`

## Phase 4: Final verification

**Owner:** `claude`

**Routing Notes:** Verification and review only.

**Goal:** Confirm the full fast suite passes and CP0 active docs match the design.

**Files:**
- Verify: all changed files

**Tasks:**
1. Run the full fast skill suite.
2. Search active docs/tests for stale Auggie references.
3. Confirm context-retrieval tool roles appear in active CP0 docs/tests.
4. Run CP4 phase review against the design acceptance criteria.

**Acceptance Criteria:**
- Full fast test suite passes.
- Active CP0 files contain no Auggie references.
- Context-retrieval retrieve/map/grep roles are documented and tested.

**Reviewer Checklist:**
- Tests cover new CP0 tool contract.
- Runtime hooks, skill docs, project docs, and tests agree.
- No CP1-CP4 format drift.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh`
- `rtk grep -R "Auggie\|auggie" hooks README.md superpowers-ccg.md CLAUDE.md rules skills tests/claude-code/README.md tests/claude-code/test-cp0-context-acquisition-guards.sh`
- `rtk grep -R "context-retrieval\|codebase_retrieve\|codebase_map\|codebase_grep" hooks README.md superpowers-ccg.md CLAUDE.md rules skills tests/claude-code/README.md tests/claude-code/test-cp0-context-acquisition-guards.sh`

## Execution Handoff

Execute one phase at a time with `executing-plans`. Claude owns these phases directly because work is documentation, hooks, tests, and release metadata unless the user explicitly changes routing.
