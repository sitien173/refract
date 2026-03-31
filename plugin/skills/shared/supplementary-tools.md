# Supplementary MCP Tools (Optional Enhancements)

Supplementary tools enhance Claude's orchestration capabilities. They are **optional** — all workflows work without them via native tool fallbacks. They do NOT replace the primary routing to Codex/Gemini/Cursor.

**Design principle:** MCPs enhance performance, never block functionality. If unavailable, proceed with native tools.

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

**Fallback:** Built-in WebSearch / WebFetch (less structured)

---

### Sequential-Thinking (`mcp__mcp-sequentialthinking-tools__sequentialthinking_tools`)

**Purpose:** Multi-step structured reasoning for complex analysis.

**Use when:**
- Debugging spans 3+ components or layers
- Architectural analysis or system design decisions
- Cross-validation arbitration (divergent model outputs)
- Complex plan decomposition with interdependencies
- Hypothesis testing with multiple variables

**Auto-triggers:** "design", "architecture", "analyze tradeoffs", "complex problem", 3+ interacting parts

**Fallback:** Native reasoning (same quality, ~2x more tokens)

---

### Serena (`mcp__serena__*`)

**Purpose:** Semantic code understanding with project memory.

**Use when:**
- Symbol-aware navigation (find references, trace dependencies)
- Large codebase exploration (>10 files involved)
- Cross-session project memory and persistence
- Refactoring with dependency tracking

**Auto-triggers:** "refactor", "find all usages", "symbol tracking", file count >10

**Fallback:** Grep + Read + Glob (3x slower, same quality)

---

### Magic (`mcp__magic__*`)

**Purpose:** Modern UI component generation from 21st.dev patterns.

**Use when:**
- Generating frontend UI components (forms, navbars, modals, tables, cards)
- Design system integration with accessibility and responsiveness
- Complements Gemini MCP for frontend routing — use Magic for component patterns, Gemini for full-page layouts and styling

**Auto-triggers:** UI component requests, "button", "form", "modal", "card", "table"

**Fallback:** Gemini MCP handles all frontend work (Magic adds design-system patterns)

---

### Morphllm Fast-Apply (`mcp__morph-mcp__*`)

**Purpose:** Pattern-based bulk code editing with token efficiency.

**Use when:**
- Repeated edits across multiple files (style migration, framework updates)
- Pattern-driven transformations (rename patterns, enforce conventions)
- Bulk refactoring where semantic context is less important than pattern matching
- Token-efficient editing during plan execution

**Auto-triggers:** Multi-file pattern edits, framework migrations, style enforcement

**Fallback:** Edit tool (more manual, same result)

## Composition Patterns

### Research Phase (Brainstorming)
```
Grok Search (gather info) → Sequential (analyze & decompose) → Design output
```

### Complex Debugging
```
Sequential (decompose problem) → Grok Search (search known issues) → Serena (trace symbols) → Fix
```

### Plan Writing
```
Sequential (architectural decomposition) → Grok Search (library docs) → Plan output
```

### Frontend Implementation
```
Magic (component patterns) + Gemini MCP (full implementation) → Opus review
```

### Bulk Refactoring
```
Serena (scope & analyze) → Morphllm (execute bulk edits) → Opus review
```

## Integration with Primary Routing

Supplementary tools operate at the **orchestrator level** — Claude uses them to enhance its own analysis before/alongside routing to Codex/Gemini/Cursor.

```
1. Claude receives task
2. [Optional] Use supplementary tools for research/analysis/planning
3. Route implementation to Codex/Gemini/Cursor (primary routing)
4. [Optional] Use supplementary tools during review/integration
5. Opus reviews
```

**No fail-closed gate** for supplementary tools. If unavailable, proceed without them.
