# Karpathy LLM Wiki + CCG Integration Plan

**Date:** 2026-05-04  
**Design:** `docs/plans/2026-05-04-karpathy-llm-wiki-ccg-integration-design.md`

## Assumptions

- Implement a thin bundled skill adapted from upstream `karpathy-llm-wiki`, not a full vendor copy of the upstream repo and assets.
- Use `docs/wiki/` as the default project-local wiki root.
- Create `docs/wiki/` only when user runs first ingest; do not ship sample wiki content unless tests need fixtures.
- Wiki affects CP0 context acquisition only; CP1 routing and executor selection stay unchanged.

## Phase Table

| Phase | Owner | Outcome |
| --- | --- | --- |
| 1 | `codex` | Add bundled LLM wiki skill with ingest/query/lint workflow and templates |
| 2 | `codex` | Wire selective `docs/wiki/` lookup into CCG CP0 instructions and prompt rules |
| 3 | `codex` | Add behavior tests and docs for skill discovery, CP0 guards, and prompt budget safety |

---

### Phase 1: Bundled wiki skill

**Owner:** `codex`

**Goal:** Add a bundled `karpathy-llm-wiki` skill that supports ingest, query, and lint operations under `docs/wiki/`.

**Files:**
- Create: `skills/karpathy-llm-wiki/SKILL.md`
- Create: `skills/karpathy-llm-wiki/references/raw-template.md`
- Create: `skills/karpathy-llm-wiki/references/article-template.md`
- Create: `skills/karpathy-llm-wiki/references/index-template.md`
- Create: `skills/karpathy-llm-wiki/references/archive-template.md`

**Tasks:**
1. Define skill metadata and triggers for ingest/query/lint: `LLM wiki`, `Karpathy wiki`, `ingest`, `add to wiki`, `what do we know`, `lint wiki`.
2. Adapt upstream workflow to use `docs/wiki/` and `docs/wiki/raw/` instead of top-level `wiki/` and `raw/`.
3. Specify first-ingest initialization rules for `docs/wiki/index.md`, `docs/wiki/log.md`, and raw/topic directories without overwriting existing files.
4. Add reference templates for raw source files, compiled articles, index entries, and archived query answers.

**Acceptance Criteria:**
- Skill clearly supports exactly three operations: ingest, query, lint.
- Storage paths consistently use `docs/wiki/` and `docs/wiki/raw/`.
- Query/lint fail gracefully when wiki has not been initialized: tell user to run ingest first.
- Raw source immutability and source citation rules are explicit.

**Reviewer Checklist:**
- No top-level `raw/` or `wiki/` paths remain in skill instructions except as contrast/examples.
- Ingest always performs both source capture and wiki compilation.
- Query answers require citations to `docs/wiki/...` pages.
- Lint distinguishes deterministic auto-fixes from heuristic report-only findings.

**Integration Checks:**
- `rtk ./tests/claude-code/run-skill-tests.sh --test test-skill-discovery.sh`
- Manual check: `skills/karpathy-llm-wiki/SKILL.md` exists and references `docs/wiki/`.

---

### Phase 2: Selective CP0 wiki knowledge layer

**Owner:** `codex`

**Goal:** Update CCG workflow instructions so CP0 selectively consults `docs/wiki/` for durable knowledge before normal Auggie current-code retrieval.

**Files:**
- Modify: `skills/coordinating-multi-model-work/checkpoints.md`
- Modify: `skills/coordinating-multi-model-work/context-sharing.md`
- Modify: `skills/shared/protocol-threshold.md`
- Modify: `hooks/session-start.sh`
- Modify: `hooks/user-prompt-submit.sh`
- Modify: `superpowers-ccg.md`
- Modify: `rules/ccg-workflow.mdc`
- Modify: `rules/bounded-tasks.mdc` if prompt-budget guard needs wiki wording

**Tasks:**
1. Add CP0 selective wiki lookup rule: use `docs/wiki/` for complex planning, architecture, debugging, refactors with prior decisions, or prompts asking what project knows/decided/tried.
2. Add skip rule for trivial edits, simple version bumps, formatting, and tasks answerable from current files.
3. Define wiki-derived context artifact ids: `wiki/relevant`, `wiki/decisions`, `wiki/conflicts`, `wiki/sources`.
4. Add authority rule: current files/tests and current user request override wiki content; wiki is advisory and citation-backed.

**Acceptance Criteria:**
- CP0 order is unambiguous: decide if wiki useful → query `docs/wiki/` if useful → use Auggie for current repo state → normalize artifacts → CP1.
- Instructions say selective lookup, not always-on lookup.
- Worker prompt rules forbid full wiki dumps and preserve `HYDRATED_CONTEXT` ≤300 tokens.
- CP1 routing matrix remains unchanged.

**Reviewer Checklist:**
- No contradiction with existing CP0 rule requiring Auggie for local code context.
- Wiki lookup is described as durable knowledge retrieval, not source-of-truth code search.
- Hook reminders stay concise and do not exceed practical prompt budget.
- Canonical/derived docs do not diverge from `context-sharing.md` where relevant.

**Integration Checks:**
- `rtk ./tests/claude-code/run-skill-tests.sh --test test-token-efficiency-guards.sh`
- `rtk ./tests/claude-code/run-skill-tests.sh --test test-cp2-external-execution-guards.sh`
- Manual grep: CP0 docs include `docs/wiki/`, `selective`, and `HYDRATED_CONTEXT` guard language.

---

### Phase 3: Tests and user-facing docs

**Owner:** `codex`

**Goal:** Add tests and docs that lock in wiki skill behavior, CP0 selectivity, citation requirements, and prompt-budget safety.

**Files:**
- Modify: `README.md`
- Modify: `tests/claude-code/README.md`
- Create: `tests/claude-code/test-karpathy-llm-wiki-integration.sh`
- Modify: existing skill or token guard tests if they already cover better anchors

**Tasks:**
1. Add test coverage for skill existence, trigger wording, and `docs/wiki/` path usage.
2. Add CP0 guard assertions that wiki lookup is selective and not always-on.
3. Add prompt-budget assertions forbidding full wiki dumps into worker prompts.
4. Document user workflow: ingest source, query wiki, lint wiki, and how CCG uses wiki during CP0.

**Acceptance Criteria:**
- Tests fail if wiki skill disappears or reverts to top-level `raw/`/`wiki/` storage.
- Tests fail if CP0 wording implies always reading wiki for every task.
- README explains `docs/wiki/` storage and current-code-wins authority rule.
- Existing test suite remains green.

**Reviewer Checklist:**
- Tests assert behavior, not brittle line numbers.
- Docs keep Karpathy wiki optional and project-local.
- No new external dependency is required for normal CCG use.
- User-facing docs do not imply wiki replaces Auggie or memory.

**Integration Checks:**
- `rtk ./tests/claude-code/run-skill-tests.sh --test test-karpathy-llm-wiki-integration.sh`
- `rtk ./tests/claude-code/run-skill-tests.sh`

---

## Final Integration

Run after all phases pass:

- `rtk ./tests/claude-code/run-skill-tests.sh`
- `rtk git status --short`

Final review must verify:

- Bundled skill uses `docs/wiki/` consistently.
- CP0 wiki lookup is selective and citation-backed.
- Worker prompts remain phase-scoped and budget-safe.
- Current repository state remains authoritative over wiki content.
