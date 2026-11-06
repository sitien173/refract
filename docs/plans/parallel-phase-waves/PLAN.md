# Parallel Phase Waves Plan

**Design:** [DESIGN.md](DESIGN.md)
**Context key:** `parallel-phase-waves`
**Base:** `refs/plans/parallel-phase-waves/base` (`cf43292cd645de74253693cece85b63f8189d785`)
**Commit:** `feat(plugin): run independent plan phases in parallel worktree waves`

## Outcome & Scope

Plans may declare phase dependencies. Phases with no unmet dependency form a
wave; a multi-phase wave implements each phase concurrently in its own worktree,
then integrates and reviews each phase serially on the main checkout in plan
order. Release version becomes 2.5.0.

Preserved invariants: Coordinator owns all Git; every landed change is
independently reviewed on the main checkout; one plan commit after
consolidation; each `impl` ref is written once; a plan without `Depends on:`
lines behaves exactly as today; no server behavior change; the six-tool Refract
API is unchanged.

Out of scope: parallel jobs in one checkout; overlapping review with the next
implementation; server admission or source changes under `server/src`;
automatic dependency inference; a plugin-level wave width cap; historical
`docs/plans/*` files other than this plan.

Refinement of DESIGN.md: the handover stores wave state as two top-level keys,
`wave_base` and a flow-mapping `wave` list, instead of a nested `wave` mapping,
because `plugin/scripts/refract-stats` parses only top-level keys and
flow-mapping list items. Outside a multi-phase wave, `wave_base` is `null` and
`wave` is `[]`; a missing key reads the same way.

## Baseline Evidence

- `plugin/tests/run.sh`: exit 0; "contract tests passed", "stats tests passed", `claude plugin validate` passed, `agy plugin validate` passed with 3 pre-existing warnings.
- `(cd server && uv run pytest tests/test_smoke.py -q)`: 60 passed.
- `(cd server && uv lock --check)`: exit 0.
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`: exit 0.

### Phase 1: Plans declare dependencies and handover records wave state

**Task Guide Input:** Add an optional per-phase `Depends on:` line to the `writing-plans` template with its authoring rules, and add wave state fields to the handover schema. Use cases: a plan author marks two phases independent; a plan without the line stays sequential; the Coordinator records each wave phase's state and job.
**Goal:** The plan template and handover schema express phase dependencies and wave state.
**Invariants & Boundaries:** Existing template fields and handover fields keep their names and meaning. `checklist` keeps its flow-mapping list style. No execution behavior is described here; wave mechanics belong to Phase 2.
**Files:**
- Modify: `plugin/skills/writing-plans/SKILL.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/handover.md`
- Modify: `plugin/tests/test-contracts.sh`
**Tasks:**
1. RED then GREEN: assert and add the template line `**Depends on:** <Phase N, Phase M | none>` after `**Goal:**`, plus rules: a missing line means the previous phase; independence requires disjoint `Files:` lists and no API, schema, or fixture the other phase creates; shared files such as lockfiles or `CHANGELOG.md` force a dependency; reject cycles and unknown phase numbers.
2. RED then GREEN: assert and add `wave_base: <commit|null>` and `wave: [{ phase, state: implementing|implemented|integrating|integrated|requeued, worktree, branch, implementation_job }, ...]` to the schema block, initial values `null` and `[]`, and the field rules: a missing key reads as `null` or `[]`; `implementation_job` is set immediately after `submit` returns; `current_phase` and `job_refs` describe the phase running gates on the main checkout.
3. RED then GREEN: assert and change the checklist rule from at most one `doing` step to at most one `doing` step per phase.
**Acceptance Criteria:**
- `writing-plans/SKILL.md` template contains `**Depends on:**` and every rule in Task 1.
- `handover.md` schema contains `wave_base:` and `wave:` with all five states and the rules in Tasks 2 and 3.
- New `test-contracts.sh` assertions fail at base and pass after the change.
**Reviewer Checklist:**
- Missing `Depends on:` means sequential; no wording implies a new default.
- The `wave` list uses the same flow-mapping style as `checklist`.
- No wave execution procedure leaked into these files.
**Verification Checks:**
- `plugin/tests/run.sh`
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`

### Phase 2: Coordinator owns a single wave procedure

**Task Guide Input:** Create the wave procedure reference and wire its exceptions into the Coordinator contract, tool contract, review procedure, and anchors. Use cases: a multi-phase wave runs implementation concurrently; a single-phase wave runs exactly as today; integration fails and the phase is requeued; a session resumes mid-wave.
**Goal:** `references/waves.md` is the single owner of wave mechanics and every existing contract points to it.
**Invariants & Boundaries:** The sentence "Submit sequential jobs one at a time" stays verbatim. Every existing guarded sentence in `test-contracts.sh` keeps passing. `job_integrate`, `integration_base`, `integration_conflict`, `execution worktree`, and `isolated worktree` stay forbidden in every workflow file. Execution skills and worker-facing files are Phase 3 and Phase 4.
**Files:**
- Create: `plugin/skills/coordinating-multi-model-work/references/waves.md`
- Modify: `plugin/skills/coordinating-multi-model-work/SKILL.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/review.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/git-anchors.md`
- Modify: `plugin/tests/test-contracts.sh`
**Tasks:**
1. RED then GREEN: create `waves.md` from DESIGN.md "Wave selection", "Multi-phase wave" steps 1 to 7, "Resume additions", and "Errors and Edge Cases", using the `wave_base` and `wave` keys from Phase 1. Assert its key rules: single-phase wave runs without a worktree; worktree creation failure runs the wave sequentially and never shares a checkout; round-robin `wait` with `timeout_s=60` while more than one job is active; `git merge --ff-only`; rebase conflict or check failure sets `requeued`; baseline commands run with phase checks before fast-forward.
2. RED then GREEN: in `SKILL.md`, link `waves.md`; after "Submit sequential jobs one at a time." add one sentence naming wave implementation jobs in separate worktrees as the sole exception; add the source-freeze exception that the Coordinator may edit main-checkout `.handover.md` while wave jobs are active.
3. RED then GREEN: in `tool-contract.md` Waiting and results, add the round-robin exception that points to `waves.md`; in `review.md`, exclude `.handover.md` from the root-unchanged check during a wave; in `git-anchors.md`, define phase `base` as HEAD before the phase lands on the plan branch, identical to today for sequential phases.
4. RED then GREEN: narrow the `test-contracts.sh` forbidden-pattern scan so only `waves.md` is exempt from the `git worktree` pattern; assert the other forbidden patterns still match nothing in `waves.md`.
**Acceptance Criteria:**
- `waves.md` exists and every Task 1 rule is asserted by `test-contracts.sh`.
- `grep -c 'Submit sequential jobs one at a time.' plugin/skills/coordinating-multi-model-work/SKILL.md` prints `1`.
- A `job_integrate` string added to `waves.md` makes `plugin/tests/test-contracts.sh` fail.
- New assertions fail at base and pass after the change.
**Reviewer Checklist:**
- `waves.md` matches DESIGN.md approach B and does not reintroduce parallel review in worktrees.
- Each `impl` ref is still written once; no failed attempt writes an anchor.
- No other file duplicates wave steps instead of linking `waves.md`.
- The guard exemption is file-scoped, not directory-scoped.
**Verification Checks:**
- `plugin/tests/run.sh`
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`

### Phase 3: Execution skills and commands run waves

**Task Guide Input:** Make `executing-plans` run one wave per invocation and `executing-plans-autonomously` loop waves, and update both command descriptions. Use cases: `/refract:execute-plan` on a sequential plan; `/refract:execute-plan` on a wave of three phases; `/refract:execute-plan-all` with a phase that exceeds Gate 2 bounds.
**Goal:** Both execution paths select and run waves through `waves.md`.
**Invariants & Boundaries:** A single-phase wave follows the existing workflow steps unchanged. The phase report format is unchanged and emitted once per phase. The zero-pause policy stays; it requeues instead of blocking. No wave mechanics are restated; link `waves.md`.
**Files:**
- Modify: `plugin/skills/executing-plans/SKILL.md`
- Modify: `plugin/skills/executing-plans-autonomously/SKILL.md`
- Modify: `plugin/commands/execute-plan.md`
- Modify: `plugin/commands/execute-plan-all.md`
- Modify: `plugin/tests/test-contracts.sh`
**Tasks:**
1. RED then GREEN: `executing-plans` resolves the next wave from `Depends on:` and `impl` refs, runs a single-phase wave through the existing steps, runs a multi-phase wave through `waves.md`, emits one phase report per phase, then stops; a failed wave phase sets `BLOCKED` after the other phases integrate.
2. RED then GREEN: `executing-plans-autonomously` loops waves until every phase has `impl`, sets a failed wave phase `requeued` and logs the decision to `.handover.md` instead of blocking.
3. RED then GREEN: the two command files say "one wave" and "all waves" respectively.
**Acceptance Criteria:**
- Both skills link `waves.md` and state the single-phase fast path.
- `executing-plans` "Constraints" no longer says one phase per invocation; it says one wave per invocation.
- New assertions fail at base and pass after the change.
**Reviewer Checklist:**
- Sequential plans hit no new step.
- The autonomous policy still never stops in `BLOCKED`.
- Dependents of a `requeued` phase wait for its `impl`.
**Verification Checks:**
- `plugin/tests/run.sh`
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`

### Phase 4: Workers run isolated with central records

**Task Guide Input:** Separate the worker code root from the plan records root, and give `using-git-worktrees` a wave mode. Use cases: a wave worker edits code in its phase worktree and appends records to the main checkout; worktree creation for a wave fails; a sequential worker runs exactly as today.
**Goal:** Wave workers edit only their worktree and write records to the main checkout by absolute path, and wave worktrees never fall back to a shared checkout.
**Invariants & Boundaries:** Sequential dispatch text keeps its meaning: code root and records root are the same `<repo-root>`. `FILES MODIFIED` stays repository-relative. Workers still never run Git commits, resets, stashes, branch changes, or ref writes. The interactive single-worktree behavior of `using-git-worktrees` is unchanged.
**Files:**
- Modify: `plugin/skills/executing-plans/implementer-prompt.md`
- Modify: `plugin/shared/worker-contract.md`
- Modify: `plugin/shared/erp.md`
- Modify: `plugin/skills/using-git-worktrees/SKILL.md`
- Modify: `plugin/tests/test-contracts.sh`
**Tasks:**
1. RED then GREEN: `implementer-prompt.md` dispatch envelope distinguishes `<code-root>` and `<records-root>` with absolute record paths; both equal `<repo-root>` outside a wave.
2. RED then GREEN: `worker-contract.md` and `erp.md` state that records are written under `<records-root>` and that `FILES MODIFIED` lists repository-relative paths from both roots.
3. RED then GREEN: `using-git-worktrees` adds a wave mode invoked by `waves.md`: one worktree per wave phase on branch `refract/<slug>/phase-<NN>` from `wave_base`, the same directory selection and ignore check, and on creation failure report and return failure instead of running in the current directory.
**Acceptance Criteria:**
- The dispatch envelope names both roots and the sequential case maps both to `<repo-root>`.
- `using-git-worktrees` wave mode forbids the current-directory fallback.
- New assertions fail at base and pass after the change.
**Reviewer Checklist:**
- No worker instruction allows writing outside `<code-root>` except the phase `notes.md` and `journal.md` under `<records-root>`.
- The sandbox-blocked write path ends in ERP `BLOCKED`, matching `waves.md`.
**Verification Checks:**
- `plugin/tests/run.sh`
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`

### Phase 5: Status output shows wave progress

**Task Guide Input:** Teach `refract-stats` to show wave phases and states in its summary, statusline, and hook output. Use cases: a handover with an active wave; a handover without wave keys; a handover with `wave: []`.
**Goal:** `refract-stats` reports each wave phase and its state without changing output for handovers outside a wave.
**Invariants & Boundaries:** Output for the existing `test-stats.sh` fixture stays byte-identical. Parsing stays stdlib-only and reuses `parse_front_matter` and `item_field`.
**Files:**
- Modify: `plugin/scripts/refract-stats`
- Modify: `plugin/tests/test-stats.sh`
**Tasks:**
1. RED: add a fixture plan whose handover has `wave_base` and a two-item `wave` list with states `implementing` and `integrated`; assert statusline and hook output contain each phase number with its state.
2. GREEN: read `wave` in `plan_stats` and render it in all three output modes only when the list is non-empty.
3. Keep the existing fixture assertions unchanged and passing.
**Acceptance Criteria:**
- The existing statusline assertion string is unchanged in `test-stats.sh` and passes.
- The wave fixture assertions fail at base and pass after the change.
**Reviewer Checklist:**
- Empty or missing `wave` adds no characters to any output.
- No new dependency or import beyond the stdlib.
**Verification Checks:**
- `plugin/tests/run.sh`
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`

### Phase 6: Release 2.5.0 with documentation

**Task Guide Input:** Bump the unified version from 2.4.0 to 2.5.0 in every location the contract and server tests check, document waves in the plugin README, and add a CHANGELOG entry. Use case: a release reader learns how to declare `Depends on:` and what a wave does.
**Goal:** Every version location reads 2.5.0 and waves are documented.
**Invariants & Boundaries:** Only version strings change in server files; no file under `server/src` changes. The existing `## Unreleased - 2026-11-03` CHANGELOG entries are kept.
**Files:**
- Modify: `plugin/.claude-plugin/plugin.json`
- Modify: `plugin/.antigravity-plugin/plugin.json`
- Modify: `plugin/.codex-plugin/plugin.json`
- Modify: `plugin/package.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `plugin/shared/erp.md`
- Modify: `plugin/shared/worker-contract.md`
- Modify: `plugin/shared/notes-template.md`
- Modify: `plugin/shared/journal-template.md`
- Modify: `plugin/tests/test-contracts.sh`
- Modify: `sonar-project.properties`
- Modify: `README.md`
- Modify: `server/README.md`
- Modify: `server/CLI_ARGUMENTS.md`
- Modify: `server/pyproject.toml`
- Modify: `server/uv.lock`
- Modify: `server/tests/test_smoke.py`
- Modify: `CHANGELOG.md`
- Modify: `plugin/README.md`
**Tasks:**
1. Replace `2.4.0` with `2.5.0` in every file above except `CHANGELOG.md` and `plugin/README.md`, including the four `refract-shared-version` markers, `test-contracts.sh:96`, and `test_smoke.py:47-48`.
2. Add a `## 2.5.0 - <release date>` CHANGELOG section above `## Unreleased - 2026-11-03` describing `Depends on:`, waves, and the unchanged sequential behavior.
3. Add a "Parallel phases" section to `plugin/README.md` covering `Depends on:`, waves, the single-phase fast path, and the four-active-job question limit.
**Acceptance Criteria:**
- The exclusion-scoped search used for the baseline, `grep -rn --exclude-dir=node_modules --exclude-dir=docs --exclude-dir=dist --exclude-dir=coverage --exclude=CHANGELOG.md -F "2.4.0" . | grep -v "web/"`, prints nothing.
- All verification checks pass.
**Reviewer Checklist:**
- No version location was missed or edited outside its version string.
- CHANGELOG and README describe only behavior delivered by Phases 1 to 5.
**Verification Checks:**
- `plugin/tests/run.sh`
- `(cd server && uv run pytest tests/test_smoke.py -q)`
- `(cd server && uv lock --check)`
- `git diff --exit-code refs/plans/parallel-phase-waves/base -- server/src`

## Final Completion Audit

After Phase 6, before consolidation, the Coordinator runs the manual smoke from
DESIGN.md "Testing" on a scratch repository: a two-phase plan with
`**Depends on:** none` on both phases shows two active jobs in two projects in
`list`, both phases fast-forward onto the plan branch and are reviewed on the
main checkout, and consolidation yields one commit. Record the result in the
Phase 6 journal.
