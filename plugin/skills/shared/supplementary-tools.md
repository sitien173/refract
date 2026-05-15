# Supplementary MCP Tools (Optional Enhancements)

Supplementary tools enhance Claude's orchestration capabilities. They are **optional** for local code work and do NOT replace the primary routing to Codex/Gemini.

**Design principle:** MCPs enhance performance without replacing the core routing workflow. For web research, Grok Search is the required path; if it is unavailable, report the failure explicitly instead of switching to a native web search fallback.

## Tool Reference

### Grok Search / Tavily (`mcp__grok-search__web_search`, `mcp__grok-search__web_fetch`, `mcp__grok-search__web_map`)

**Purpose:** Web search and real-time information retrieval (Grok Search wraps Tavily).

**Tools:**
- `mcp__grok-search__web_search` — deep web search with Tavily-powered results
- `mcp__grok-search__web_fetch` — fetch and extract full page content as Markdown
- `mcp__grok-search__web_map` — map website structure by graph traversal
- `mcp__grok-search__get_sources` — retrieve source list for a search session

**Use when:**
- Research phase in brainstorming (current events, competitive analysis)
- Debugging: searching for known issues, error messages, library bugs
- Plan writing: gathering context about unfamiliar libraries/APIs
- Any task needing information beyond model knowledge cutoff

**Auto-triggers:** "search", "latest", "current trends", "find error solution", unknown error messages

**Fallback:** Report the failure explicitly; do not silently switch to native web search tools

---

### Context-Retrieval Code Search (mcp__context-retrieval__codebase-retrieval)

**Purpose:** Current local code context retrieval across a repository.

**Use when:**
- Mandatory CP0 local context acquisition before CP1 on every task
- You need semantic anchors, architecture relationships, or exact references before routing

**Auto-triggers:** "where does", "what handles", "how is", unfamiliar subsystem or workflow, known identifier sweeps

**Fail-closed:** `BLOCKED` on failure per `skills/coordinating-multi-model-work/checkpoints.md` CP0 section.

---

### Stellaris Code Search (`mcp__stellaris__search_code`, `mcp__stellaris__get_file_outline`, `mcp__stellaris__get_file_folded`, `mcp__stellaris__get_symbol`)

**Purpose:** Optional secondary CP0 local code context retrieval using LanceDB + tree-sitter + FTS5 + vector search + RRF (Reciprocal Rank Fusion). Uses Voyage AI voyage-code-3 embeddings with optional Voyage/Cohere reranking.

**Tools:**
- `mcp__stellaris__search_code` — semantic code search (code-specific embeddings, AST-aware)
- `mcp__stellaris__get_file_outline` — file structure with top-level symbols and line ranges
- `mcp__stellaris__get_file_folded` — signatures + JSDoc under a token budget (no bodies)
- `mcp__stellaris__get_symbol` — full source of one symbol with file context

**Use when:**
- CP0 local context acquisition alongside mandatory `codebase-retrieval` (run both in parallel)
- Symbol-level precision needed (function signatures, class outlines, type definitions)
- AST-aware search for code structure relationships
- Token-efficient file exploration (outline → folded → symbol drill-down)

**Auto-triggers:** symbol lookup, function signature, class hierarchy, type definition, code structure exploration

**Not fail-closed:** Stellaris failure does NOT block CP0. Only `codebase-retrieval` failure triggers `BLOCKED`.

## Composition Patterns

### CP0 Context Retrieval
```
codebase-retrieval (mandatory) + stellaris search_code (optional, parallel) → merge into CONTEXT_ARTIFACTS → Grok Search (only if external/current knowledge or research is required after local retrieval succeeds)
```

### Research Phase (Brainstorming)
```
Grok Search (gather info) → Design output
```

### Complex Debugging
```
context-retrieval via `codebase-retrieval` (mandatory local context) → Grok Search (search known issues if needed) → Fix
```

### Plan Writing
```
Grok Search (library docs if needed) → Plan output
```

## Integration with Primary Routing

Supplementary tools operate at the **orchestrator level** — Claude uses them to enhance its own analysis before/alongside routing to Codex/Gemini. They do not replace the primary CP0→CP4 workflow in `skills/coordinating-multi-model-work/checkpoints.md`.

