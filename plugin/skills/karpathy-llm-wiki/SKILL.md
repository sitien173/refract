---
name: karpathy-llm-wiki
description: "Project-local LLM wiki workflow for ingest, query, and lint. Use when: LLM wiki, Karpathy wiki, ingest, add to wiki, what do we know, lint wiki."
---

# Karpathy LLM Wiki

## Overview

Maintain a project-local LLM wiki under `docs/wiki/`. This is a thin workflow adapted from Karpathy-style LLM wiki habits: preserve raw sources, compile durable articles, query with citations, and lint for drift.

This skill supports exactly three operations:

1. `ingest` — capture source material and compile wiki pages.
2. `query` — answer from initialized wiki pages with citations.
3. `lint` — check wiki consistency and report or apply safe fixes.

Upstream examples may use top-level storage; this skill always uses `docs/wiki/` and `docs/wiki/raw/`.

## Storage

- Root: `docs/wiki/`
- Raw sources: `docs/wiki/raw/<topic>/YYYY-MM-DD-slug.md`
- Compiled pages: `docs/wiki/<topic>/<article>.md`
- Index: `docs/wiki/index.md`
- Operation log: `docs/wiki/log.md`
- Optional query archive: `docs/wiki/archive/YYYY-MM-DD-slug.md`

Raw sources are immutable after ingest. Do not edit, rewrite, normalize, or delete raw source files once captured. If a source needs correction, ingest a new raw source and link both records.

Compiled pages may be updated, split, merged, and cross-linked as knowledge changes. Every compiled claim sourced from ingested material must cite `docs/wiki/raw/...` or another `docs/wiki/...` page.

## Operation: ingest

Use for prompts like `ingest this`, `add this to wiki`, `save this source to the LLM wiki`, or `add this to Karpathy wiki`.

### First-ingest initialization

Before first ingest, create only missing paths and files:

1. Create `docs/wiki/` if missing.
2. Create `docs/wiki/raw/` if missing.
3. Create `docs/wiki/index.md` from `references/index-template.md` if missing.
4. Create `docs/wiki/log.md` if missing.
5. Create topic directories under `docs/wiki/raw/<topic>/` and `docs/wiki/<topic>/` only as needed.

Never overwrite existing wiki files during initialization.

### Ingest workflow

1. Read or fetch source material provided by user.
2. Choose short stable topic slug.
3. Choose source slug from title/date/source identity.
4. Save raw source at `docs/wiki/raw/<topic>/YYYY-MM-DD-slug.md` using `references/raw-template.md`.
5. Treat saved raw file as immutable.
6. Compile or update one or more pages under `docs/wiki/<topic>/` using `references/article-template.md`.
7. Update `docs/wiki/index.md` with topic/article links using `references/index-template.md` conventions.
8. Append operation to `docs/wiki/log.md`.
9. Report created/updated paths and cite raw source path.

Ingest is incomplete unless both source capture and wiki compilation happen.

## Operation: query

Use for prompts like `what do we know about X`, `search LLM wiki for X`, or `what did we decide about X`.

If `docs/wiki/index.md` or `docs/wiki/raw/` is missing, fail gracefully: say wiki has not been initialized and tell user to run an ingest first.

### Query workflow

1. Read `docs/wiki/index.md` first.
2. Select only relevant `docs/wiki/...` pages.
3. Read raw sources only when compiled pages need verification or source detail.
4. Answer from wiki content only when evidence exists.
5. Cite each factual claim with `docs/wiki/...` paths.
6. If wiki evidence conflicts with current repository files or user request, say so; current files and current user request win.

Do not dump full wiki contents into response or worker prompts. Summarize relevant facts and cite pages.

## Operation: lint

Use for prompts like `lint wiki`, `check wiki`, or `validate LLM wiki`.

If `docs/wiki/index.md` or `docs/wiki/raw/` is missing, fail gracefully: say wiki has not been initialized and tell user to run an ingest first.

### Lint workflow

1. Check `docs/wiki/index.md` links point to existing compiled pages.
2. Check compiled pages cite `docs/wiki/...` sources for sourced claims.
3. Check raw source paths follow `docs/wiki/raw/<topic>/YYYY-MM-DD-slug.md`.
4. Check raw files were not edited during lint.
5. Check `docs/wiki/log.md` includes ingest/query/lint entries when present.
6. Report stale, missing, duplicate, or conflicting claims with paths.

### Deterministic auto-fixes

Safe to apply after reporting:

- Add missing index links for existing compiled pages.
- Remove broken index links to missing compiled pages.
- Normalize relative wiki links to `docs/wiki/...` paths.
- Append lint entry to `docs/wiki/log.md`.

### Heuristic report-only findings

Do not auto-fix without user approval:

- Merge or split compiled articles.
- Resolve conflicting claims.
- Delete sources or compiled pages.
- Rewrite summaries or conclusions.
- Infer missing citations when source is ambiguous.

## References

- `references/raw-template.md`
- `references/article-template.md`
- `references/index-template.md`
- `references/archive-template.md`
