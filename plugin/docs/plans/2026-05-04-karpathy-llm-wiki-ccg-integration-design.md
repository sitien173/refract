# Karpathy LLM Wiki + CCG Integration Design

## Goal

Integrate `karpathy-llm-wiki` into Superpowers-CCG in two ways:

1. Bundle an LLM wiki skill users can invoke for ingest, query, and lint operations.
2. Wire CCG CP0 to selectively use `docs/wiki/` as a durable knowledge layer for complex workflow tasks.

The integration should preserve CCG's existing architecture: Claude remains planner/orchestrator/reviewer/integrator, Codex remains the default executor, Gemini remains UI-heavy only, and worker prompts stay phase-scoped with strict context budgets.

## Storage Model

Use `docs/wiki/` as the default project-local knowledge store.

```text
docs/wiki/
├── index.md              # Table of contents and topic summaries
├── log.md                # Append-only operation log
├── raw/                  # Immutable source material
│   └── <topic>/
│       └── YYYY-MM-DD-slug.md
└── <topic>/              # Compiled knowledge pages
    └── article-name.md
```

`raw/` files are immutable after ingest. Compiled wiki pages may be updated, split, merged, and cross-linked as knowledge compounds over time.

## Bundled Skill

Add a bundled skill, likely `skills/karpathy-llm-wiki/SKILL.md`, with three operations:

### Ingest

Triggered by prompts like "ingest this", "add this to wiki", or "save this source to the LLM wiki".

Flow:

1. Fetch or read the source.
2. Pick or create a topic under `docs/wiki/raw/`.
3. Save source as `docs/wiki/raw/<topic>/YYYY-MM-DD-slug.md`.
4. Compile or update one or more pages under `docs/wiki/<topic>/`.
5. Update `docs/wiki/index.md`.
6. Append operation details to `docs/wiki/log.md`.

If new source conflicts with existing wiki content, preserve both claims with source attribution instead of overwriting silently.

### Query

Triggered by prompts like "what do we know about X?", "query the wiki", or "from the LLM wiki...".

Flow:

1. Start from `docs/wiki/index.md`.
2. Read only relevant topic pages.
3. Answer with citations to `docs/wiki/...` pages.
4. If wiki is missing, tell user to run an ingest first.

### Lint

Triggered by prompts like "lint wiki" or "check wiki health".

Deterministic checks may auto-fix:

- Missing or stale `index.md` entries.
- Broken internal wiki links.
- Missing raw source references.
- Bad See Also links within topic pages.

Heuristic checks report only:

- Stale summaries.
- Weak citations.
- Duplicate pages.
- Contradictions needing human review.

## CCG CP0 Integration

CP0 gains a selective wiki lookup step. It must not query the wiki for every task.

Use `docs/wiki/` during CP0 when the task is:

- Complex implementation planning.
- Architecture or design work.
- Debugging with possible historical context.
- Refactoring where prior decisions matter.
- Any prompt asking what the project knows, decided, tried, or documented.

Skip wiki lookup for trivial edits, one-shot formatting, simple version bumps, and tasks fully answerable from current files.

Recommended CP0 order:

1. Decide whether durable knowledge is likely useful.
2. If yes, query `docs/wiki/index.md` and relevant wiki pages.
3. Use Auggie for current repo state.
4. Normalize both into small context artifacts.
5. Proceed to CP1 routing.

Useful artifact ids:

- `wiki/relevant`
- `wiki/decisions`
- `wiki/conflicts`
- `wiki/sources`
- `req/core`
- `files/hotspots`
- `verify/commands`

Worker prompts should receive only small wiki excerpts when directly useful. Full wiki pages must not be pasted into `HYDRATED_CONTEXT`; current 300-token hard cap still applies.

## Authority Rules

Wiki content is advisory, not authoritative over current repository state.

Priority order:

1. Current files and tests.
2. Current user request.
3. Wiki pages with citations.
4. Raw source material.
5. Memory or prior conversation summaries.

If wiki conflicts with current files, trust current files and optionally report stale wiki content. If source material conflicts with compiled wiki pages, update the compiled page with a conflict note and source attribution.

## Prompt and Workflow Changes

Update CCG workflow docs to mention selective wiki lookup in CP0:

- `skills/coordinating-multi-model-work/checkpoints.md`
- `skills/coordinating-multi-model-work/context-sharing.md`
- `skills/shared/protocol-threshold.md`
- `hooks/session-start.sh`
- `hooks/user-prompt-submit.sh`
- `superpowers-ccg.md`
- `README.md` if user-facing install/usage docs are needed

Do not change CP1 routing rules. Wiki integration affects context acquisition only, not executor selection.

## Testing Strategy

Add or update tests for:

1. Skill discoverability and trigger wording for ingest/query/lint.
2. CP0 instructions say wiki lookup is selective, not always-on.
3. Prompt templates forbid full wiki dumps and preserve `HYDRATED_CONTEXT` cap.
4. Lint behavior checks `docs/wiki/index.md` against compiled pages.
5. Query behavior requires citations to `docs/wiki/...` pages.

## Risks and Mitigations

### Stale wiki content

Mitigation: current files win. Wiki answers cite pages so stale claims are traceable.

### Prompt bloat

Mitigation: index-first search, relevant pages only, artifact summaries, 300-token hydrated excerpts.

### Conflicting knowledge

Mitigation: preserve disagreements with source attribution. Do not silently overwrite claims.

### Overlap with Auggie

Mitigation: Auggie provides current code context. Wiki provides durable synthesized project knowledge and prior decisions.

### Docs clutter

Mitigation: keep all wiki material isolated under `docs/wiki/` with clear `index.md` and `log.md`.

## Open Questions

- Should bundled skill be a direct fork/copy of upstream `karpathy-llm-wiki`, or should Superpowers-CCG implement a thinner compatibility layer?
- Should `docs/wiki/raw/` be included in package examples, or only created on first ingest?
- Should wiki lint be exposed as a standalone test command in `tests/claude-code/`?

## Success Criteria

- Users can ingest, query, and lint a project-local LLM wiki under `docs/wiki/`.
- CP0 selectively consults the wiki for complex tasks without slowing trivial edits.
- Wiki context flows into normal CCG `CONTEXT_ARTIFACTS`.
- Worker prompts stay narrow and never receive full wiki dumps.
- Current repository state remains authoritative over wiki content.
