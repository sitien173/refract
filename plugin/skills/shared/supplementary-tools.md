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

### Auggie Code Search (`mcp__auggie__augment_code_search`)

**Purpose:** Semantic "where/what/how" search across a repository.

**Use when:**
- Starting CP0 context acquisition in an unfamiliar code area
- You need concept-level search instead of exact keyword grep
- You want likely implementation anchors before narrowing to symbols

**Auto-triggers:** "where does", "what handles", "how is", unfamiliar subsystem or workflow

**Fallback:** Native file search (`rg`, `glob`, `read`)

## Composition Patterns

### CP0 Context Retrieval
```
Auggie (full local codebase context retrieval) → Grok Search (only if external/current knowledge or research is required)
```

### Research Phase (Brainstorming)
```
Grok Search (gather info) → Design output
```

### Complex Debugging
```
Auggie (retrieve local context) → Grok Search (search known issues if needed) → Fix
```

### Plan Writing
```
Grok Search (library docs if needed) → Plan output
```

## Integration with Primary Routing

Supplementary tools operate at the **orchestrator level** — Claude uses them to enhance its own analysis before/alongside routing to Codex/Gemini.

```
1. Claude receives task
2. CP0: use Auggie for local context acquisition; use Grok Search only for external/current research
3. Route implementation to Codex first or Gemini for UI-heavy phases at CP1 (primary routing)
4. [Optional] Use supplementary tools during review/integration
5. Claude runs CP4 phase review
```

**No fail-closed gate** for local supplementary tools. If Grok Search is required for web research and unavailable, report the failure instead of using a native web-search fallback.
