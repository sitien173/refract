# Superpowers-CCG

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow and adds **CCG multi-model orchestration**: Claude plans phases, routes execution, reviews outputs, and runs integration checks. **Codex MCP** is the default executor for most implementation. **Gemini MCP** is reserved for UI-heavy phases.

> **CCG** = **C**laude + **C**odex + **G**emini

## What You Get

- **Claude as planner/reviewer/integrator**: Claude creates phases, routes execution, reviews output, and runs integration gates.
- **Practical model routing (CCG)**: Codex first for most implementation. Gemini only for UI-heavy phases. Use **CROSS_VALIDATION** only for unresolved architecture conflicts.
- **Phase review**: CP4 returns `PASS`, `PASS_WITH_DEBT`, or `FAIL` against the original request, CP1 success criteria, reviewer checklist, and integration checks.
- **MCP tool integration**: external calls go through `mcp__codex__codex` and `mcp__gemini__gemini`.
- **Collaboration checkpoints**: CP0/CP1/CP2/CP3/CP4 checkpoints are embedded in the main skills.
- **Smart context sharing**: CP0 produces reusable context artifacts, CP1 builds budgeted phase-scoped bundles, and same-phase follow-ups send deltas only.
- **Project-local LLM wiki**: optional `karpathy-llm-wiki` skill stores durable knowledge under `docs/wiki/` and lets CP0 selectively use it when useful.
- **Fail-closed executor gate**: if Codex or Gemini MCP execution fails, the phase stops with `BLOCKED`; no retry or executor switch.

## Platform Support

Superpowers-CCG supports Claude Code through the Claude plugin, hooks, commands, agents, and skills in this repository.

## Quick Start

#### Prerequisites

- [Claude Code](https://docs.claude.com/docs/claude-code) installed (`claude --version`)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed and authenticated (`gemini --version`)
- [Codex CLI](https://developers.openai.com/codex/quickstart) installed and authenticated (`codex --version`)
- `uv` / `uvx` available

#### Install

```bash
claude plugin marketplace add https://github.com/sitien173/superpowers-ccg
claude plugin install superpowers-ccg
```

#### MCP Setup

```bash
# Backend and systems specialist
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp

# UI-heavy specialist
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
```

## Using External Models

You normally do **not** call MCP tools manually. Tell Claude what you want, and the workflow decides when to invoke external models.

- Default implementation: "Use Codex MCP and return the final files directly."
- UI-heavy phase: "Use Gemini MCP for visual layout/components/styles/interactions and return the final files directly."
- Cross-validation: "Do CROSS_VALIDATION for this design and reconcile conflicts."
- CP4 phase review and integration checks run after every phase. Final summary happens after all phases.

## Model Selection

| Task type | Routing | MCP Tool |
|---|---|---|
| Backend, full-stack, tests, debugging, scripts, CI/CD, Docker, infrastructure | CODEX | `mcp__codex__codex` |
| UI-heavy visual work (layout, styling, motion, canvas/SVG, interactions) | GEMINI | `mcp__gemini__gemini` |
| Unresolved architecture conflict | CROSS_VALIDATION | multiple |
| Planning, review, integration, docs, coordination | CLAUDE | none |

The routing and checkpoint rules live in `skills/coordinating-multi-model-work/`.

## Checkpoint Protocol

| Checkpoint | When | Purpose |
|---|---|---|
| CP0 | Before CP1 | Selective `docs/wiki/` durable knowledge lookup when useful, then Auggie for current local code context and Grok Search for external research |
| CP1 | Immediately after CP0, before first executor call | Phase assessment and routing using the CP1 routing matrix |
| CP2 | After CP1 when routed externally | External execution via Codex/Gemini/Cross-Validation with final file output |
| CP3 | After CP2 when reconciliation is needed | Resolve external-model conflicts, gaps, and clarifications before CP4 |
| CP4 | After each phase | Phase review against the original request, CP1 success criteria, reviewer checklist, and integration results |

## Project-local LLM Wiki

The bundled `karpathy-llm-wiki` skill keeps optional durable project knowledge in `docs/wiki/`:

- **Ingest** source material into `docs/wiki/raw/<topic>/YYYY-MM-DD-slug.md`, then compile or update cited articles under `docs/wiki/<topic>/`.
- **Query** initialized wiki pages for prompts like "what do we know about X" and answer with `docs/wiki/...` citations.
- **Lint** wiki structure, citations, and index links; deterministic fixes are separate from heuristic report-only findings.

`docs/wiki/` is created only on first ingest. CP0 uses it selectively for complex planning, architecture, debugging, refactors with prior decisions, or prompts asking what was known/decided/tried. Trivial edits and tasks answerable from current files skip wiki lookup. Current files, tests, and the current user request override wiki content; Auggie remains the source for current code context.

## Differences vs Superpowers (obra/superpowers)

- **Claude as planner/reviewer/integrator**: Claude owns orchestration, review, integration, and final summary.
- **Built-in multi-model routing** via MCP tools (Codex, Gemini).
- **Codex-first routing**: most implementation routes to Codex; Gemini is for UI-heavy phases only.
- **CP4 phase review**: review returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`; broad style review is not part of the checkpoint flow unless the phase checklist requires it.
- **CP checkpoints** enforce evidence-driven collaboration.
- **Skill set changes** align the plugin with the CCG workflow.

## Update

```bash
claude plugin update superpowers-ccg
```

## Testing

```bash
./tests/claude-code/run-skill-tests.sh
```

See `tests/claude-code/README.md` for the Claude Code suite, including slower integration coverage.

## Support

- Issues: https://github.com/sitien173/superpowers-ccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) - Original Superpowers project
- [BryanHoo/superpowers-ccg](https://github.com/BryanHoo/superpowers-ccg) - CCG collaboration fork
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [Danau5tin/multi-agent-coding-system](https://github.com/Danau5tin/multi-agent-coding-system) - Smart context-sharing inspiration
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
