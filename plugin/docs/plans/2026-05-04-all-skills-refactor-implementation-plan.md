# All Skills Refactor Implementation Plan

Design source: `docs/plans/2026-05-04-all-skills-refactor-design.md`

## Phase Table

| Phase | Owner | Outcome |
| --- | --- | --- |
| 1 | `claude` | Add static guardrails for skill best-practices contracts before content edits |
| 2 | `claude` | Consolidate canonical shared references and reduce workflow drift |
| 3 | `claude` | Compress all `SKILL.md` files to concise entry points with direct references |
| 4 | `claude` | Verify behavior, docs clarity, and token-efficiency guardrails |

---

### Phase 1: Skill contract guardrails

**Owner:** `claude`

**Goal:** Add or extend static tests that lock in skill frontmatter, concise entry points, one-level references, and exact CCG checkpoint contracts before refactoring content.

**Files:**
- Modify: `tests/claude-code/run-skill-tests.sh`
- Modify: `tests/claude-code/test-token-efficiency-guards.sh`
- Modify: `tests/claude-code/test-namespace-consistency.sh`
- Create or modify: `tests/claude-code/test-skill-structure-guards.sh`
- Modify: `tests/claude-code/README.md`

**Tasks:**
1. Add a static structure guard for `skills/*/SKILL.md` frontmatter: lowercase hyphen `name`, non-empty third-person `description`, max description length, and required sections for compact skill entry points.
2. Add one-level reference checks for Markdown links from `SKILL.md` files, allowing direct references to `skills/shared/` and same-skill `references/` files while rejecting nested reference chains.
3. Extend token-efficiency or structure guards to enforce a practical `SKILL.md` line budget with an explicit allowlist only where justified.
4. Register new guard test in `run-skill-tests.sh` and document it in `tests/claude-code/README.md`.

**Acceptance Criteria:**
- Static tests fail if a skill has invalid frontmatter, missing compact-contract sections, Windows-style reference paths, nested reference-only chains, or line-budget violations.
- Existing CP1/CP3/CP4 exact-block guard tests are not weakened.
- New guard tests are included in normal skill test runner output.

**Reviewer Checklist:**
- Test rules match the design without requiring unrelated skill renames.
- Tests are deterministic shell/static checks, not brittle prose snapshots.
- Allowlist, if any, is narrow and explained in test code or test output.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-skill-structure-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-token-efficiency-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-namespace-consistency.sh`

---

### Phase 2: Shared reference consolidation

**Owner:** `claude`

**Goal:** Make shared and coordinating references canonical, concise, and easy for compact skills to link without duplicating workflow logic.

**Files:**
- Modify: `skills/shared/protocol-threshold.md`
- Modify: `skills/shared/multi-model-integration-section.md`
- Modify: `skills/shared/supplementary-tools.md`
- Modify: `skills/coordinating-multi-model-work/context-sharing.md`
- Modify: `skills/coordinating-multi-model-work/checkpoints.md`
- Modify: `skills/coordinating-multi-model-work/routing-decision.md`
- Modify: `skills/coordinating-multi-model-work/INTEGRATION.md`
- Modify: `skills/coordinating-multi-model-work/GATE.md`
- Modify: `skills/coordinating-multi-model-work/cross-validation.md`
- Modify: `skills/coordinating-multi-model-work/review-chain.md`

**Tasks:**
1. Add small contents lists to reference files over 100 lines and ensure every reference is directly reachable from a relevant `SKILL.md` or shared reference pointer.
2. Remove duplicated long CP prose where canonical files already own the rule; keep short summaries plus direct links.
3. Preserve canonical ownership: `context-sharing.md` owns tier budgets/session policy, `protocol-threshold.md` owns CP0–CP4 required blocks, coordinating references own routing/reconciliation/review details.
4. Normalize file paths to forward slashes and fully qualify MCP tool mentions where present.

**Acceptance Criteria:**
- Shared references clearly state canonical ownership and do not contain conflicting route, budget, retry, or fail-closed rules.
- Reference files over 100 lines expose contents near top.
- Existing CP guard tests still pass after consolidation.

**Reviewer Checklist:**
- No behavioral rule is removed unless it is preserved in a direct canonical reference.
- `BLOCKED` on Codex/Gemini MCP failure remains unchanged.
- `HYDRATED_CONTEXT` 300-token hard cap remains visible in canonical context-sharing/protocol docs.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp0-context-acquisition-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp1-routing-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp2-external-execution-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp3-reconciliation-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-cp4-final-spec-review-guards.sh`

---

### Phase 3: Compact all skill entry points

**Owner:** `claude`

**Goal:** Rewrite every `skills/*/SKILL.md` into concise discovery-first entry points using the compact contract while preserving skill-specific hard rules.

**Files:**
- Modify: `skills/brainstorming/SKILL.md`
- Modify: `skills/writing-plans/SKILL.md`
- Modify: `skills/coordinating-multi-model-work/SKILL.md`
- Modify: `skills/executing-phases/SKILL.md`
- Modify: `skills/executing-plans/SKILL.md`
- Modify: `skills/debugging-systematically/SKILL.md`
- Modify: `skills/verifying-before-completion/SKILL.md`
- Modify: `skills/karpathy-llm-wiki/SKILL.md`
- Create or modify: per-skill `references/*.md` only if needed to preserve details moved out of `SKILL.md`

**Tasks:**
1. Rewrite each `SKILL.md` to follow: `Use When`, `Workflow`, `Hard Rules`, `References`.
2. Update descriptions to include capability plus activation triggers in third person without exceeding frontmatter limits.
3. Move non-entry-point detail into direct one-level references instead of deleting required behavior.
4. Preserve skill-specific constraints from the design, including brainstorming confirmation/doc write, wiki raw immutability/citations, and CCG routing/fail-closed behavior.

**Acceptance Criteria:**
- Every skill entry point is concise, scan-friendly, and direct-link based.
- All hard rules needed for safe activation remain visible in `SKILL.md` or direct references.
- No skill loses its documented completion/verification requirements.

**Reviewer Checklist:**
- Compression did not hide CP blocks, fail-closed rules, or required user-confirmation points.
- Descriptions are specific enough for skill discovery and avoid vague helper wording.
- Per-skill references are used only where needed; no unnecessary new files.

**Integration Checks:**
- `rtk env REQUIRE_COMPACT_CONTRACT=1 bash ./tests/claude-code/run-skill-tests.sh --test test-skill-structure-guards.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-executing-phases.sh`
- `rtk bash ./tests/claude-code/run-skill-tests.sh --test test-karpathy-llm-wiki-integration.sh`
- Manual check: each `skills/*/SKILL.md` has direct references only and no Windows-style paths.

---

### Phase 4: Full verification and documentation cleanup

**Owner:** `claude`

**Goal:** Verify all skill tests, update user-facing testing docs if needed, and confirm the refactor satisfies the design without token-waste regressions.

**Files:**
- Modify: `README.md` only if skill behavior or test commands in user-facing docs changed
- Modify: `tests/claude-code/README.md` if new or changed test coverage needs documentation
- Modify: `docs/testing.md` if integration-test guidance changes
- Modify: `docs/plans/2026-05-04-all-skills-refactor-implementation-plan.md` only if phase checks need correction during execution

**Tasks:**
1. Run the full fast skill test suite and fix any failures within the refactor scope.
2. Run targeted headless/integration tests only if static tests or changed orchestration wording require behavior confirmation.
3. Update testing docs for any new guard test names or changed test runner output.
4. Produce final verification summary with changed files, test results, and remaining debt if any.

**Acceptance Criteria:**
- Full fast skill suite passes.
- Any changed test names or new guardrails are documented.
- Final state satisfies design acceptance criteria: concise skills, canonical shared refs, progressive disclosure, eval guardrails.

**Reviewer Checklist:**
- Verification covers both static structure and behavior-sensitive skill workflows.
- Documentation changes are limited to test/usage updates caused by this refactor.
- No implementation commit is made unless explicitly requested.

**Integration Checks:**
- `rtk bash ./tests/claude-code/run-skill-tests.sh`
- If orchestration behavior changed materially: `rtk bash ./tests/claude-code/run-skill-tests.sh --integration --timeout 1800`
- Manual check: compare final changed files against design scope.

---

## Final Integration

Run only after all phases pass:

- `rtk git status --short`
- `rtk bash ./tests/claude-code/run-skill-tests.sh`
- Optional if orchestration behavior changed: `rtk bash ./tests/claude-code/run-skill-tests.sh --integration --timeout 1800`

Do not commit unless the user explicitly asks.

## Execution Handoff

Execute one phase at a time. Claude owns and implements each phase directly in this session; do not route these phases to Codex or Gemini unless the user explicitly changes the plan.
