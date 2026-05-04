---
name: karpathy-llm-wiki
description: "Project-local LLM wiki workflow for ingest, query, and lint operations under docs/wiki/. Use when the user mentions LLM wiki, Karpathy wiki, ingest, add to wiki, what do we know, search wiki, query wiki, lint wiki, or validate wiki."
---

# Karpathy LLM Wiki

## Use When

- User says LLM wiki, Karpathy wiki, ingest, add to wiki, what do we know, query wiki, search wiki, lint wiki, or validate wiki.
- Project-local durable knowledge should be captured or queried under `docs/wiki/`.
- CP0 needs selective wiki context as advisory, citation-backed project knowledge.

## Workflow

This skill supports exactly three operations: `ingest`, `query`, and `lint`.

### Operation: ingest

1. Initialize only missing paths: `docs/wiki/`, `docs/wiki/raw/`, `docs/wiki/index.md`, `docs/wiki/log.md`, and needed topic dirs.
2. Never overwrite existing wiki files during initialization.
3. Save raw source at `docs/wiki/raw/<topic>/YYYY-MM-DD-slug.md` using `references/raw-template.md`.
4. Raw sources are immutable after ingest; do not edit, rewrite, normalize, or delete them.
5. Compile or update pages under `docs/wiki/<topic>/` using `references/article-template.md`.
6. Update `docs/wiki/index.md` and append `docs/wiki/log.md`.
7. Ingest is incomplete unless both source capture and wiki compilation happen.

### Operation: query

1. If `docs/wiki/index.md` or `docs/wiki/raw/` is missing, say the wiki has not been initialized and tell the user to run an ingest first.
2. Read `docs/wiki/index.md` first, then only relevant compiled pages.
3. Read raw sources only when compiled pages need verification or source detail.
4. Answer from wiki evidence only; cite `docs/wiki/...` paths.
5. Cite each factual claim.
6. If wiki evidence conflicts with current repository files or current user request, say so; current files and current user request win.

### Operation: lint

1. If wiki files are missing, say the wiki has not been initialized and tell the user to run an ingest first.
2. Check index links, compiled citations, raw source paths, raw immutability, and log entries.
3. Report stale, missing, duplicate, or conflicting claims with paths.
4. Apply only deterministic safe fixes.

## Hard Rules

- Use only `docs/wiki/` and `docs/wiki/raw/`; never top-level wiki storage.
- Never overwrite existing wiki files during initialization.
- Raw sources are immutable after ingest.
- Do not dump full wiki contents into responses or worker prompts.
- Wiki content is advisory and citation-backed; current files, tests, and current user request override it.
- Deterministic auto-fixes: add missing index links, remove broken index links, normalize relative wiki links to `docs/wiki/...`, and append lint log entries.
- Heuristic report-only findings: merge/split articles, resolve conflicts, delete sources/pages, rewrite conclusions, or infer ambiguous citations.

## References

- `references/raw-template.md` — raw source format.
- `references/article-template.md` — compiled article format.
- `references/index-template.md` — wiki index format.
- `references/archive-template.md` — optional query archive format.
- `skills/shared/protocol-threshold.md` — CP0 wiki lookup rules.
- `skills/coordinating-multi-model-work/context-sharing.md` — wiki context artifact names for relevant facts, decisions, conflicts, and sources.
