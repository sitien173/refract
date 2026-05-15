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

### Stellaris Code Search (`mcp__stellaris__search_code`, `mcp__stellaris__get_file_outline`, `mcp__stellaris__get_file_folded`, `mcp__stellaris__get_symbol`)

**Purpose:** Mandatory CP0 local code context retrieval using LanceDB + tree-sitter + FTS5 + vector search + RRF (Reciprocal Rank Fusion). Uses Voyage AI voyage-code-3 embeddings with optional Voyage/Cohere reranking.

**Tools:**
- `mcp__stellaris__search_code` — semantic code search (code-specific embeddings, AST-aware, hybrid FTS5 + vector + RRF)
- `mcp__stellaris__get_file_outline` — file structure with top-level symbols and line ranges (~200 tokens)
- `mcp__stellaris__get_file_folded` — signatures + JSDoc under a token budget (no function bodies)
- `mcp__stellaris__get_symbol` — full source of one symbol with file context (imports, siblings, warnings)

**Recommended workflow:**
1. `search_code` — find features by natural language description (mandatory CP0 step)
2. `get_file_outline` — view symbols + imports/exports in matched files
3. `get_file_folded` — signatures + JSDoc under token budget
4. `get_symbol` — full source of specific symbol (only step that returns full code)

**Use when:**
- Mandatory CP0 local context acquisition before CP1 on every task
- You need semantic anchors, architecture relationships, or exact references before routing
- Symbol-level precision needed (function signatures, class outlines, type definitions)
- AST-aware search for code structure relationships
- Token-efficient file exploration (outline → folded → symbol drill-down)

**Auto-triggers:** "where does", "what handles", "how is", unfamiliar subsystem or workflow, known identifier sweeps, symbol lookup, function signature, class hierarchy, type definition

**Fail-closed:** `BLOCKED` on failure per `skills/coordinating-multi-model-work/checkpoints.md` CP0 section.

## Composition Patterns

### CP0 Context Retrieval
```
stellaris search_code (mandatory current local code context retrieval) → get_file_outline / get_file_folded / get_symbol (token-efficient drill-down) → Grok Search (only if external/current knowledge or research is required after local retrieval succeeds)
```

### Research Phase (Brainstorming)
```
Grok Search (gather info) → Design output
```

### Complex Debugging
```
stellaris search_code (mandatory local context) → Grok Search (search known issues if needed) → Fix
```

### Plan Writing
```
Grok Search (library docs if needed) → Plan output
```

## Integration with Primary Routing

Supplementary tools operate at the **orchestrator level** — Claude uses them to enhance its own analysis before/alongside routing to Codex/Gemini. They do not replace the primary CP0→CP4 workflow in `skills/coordinating-multi-model-work/checkpoints.md`.
