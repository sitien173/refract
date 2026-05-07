# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Global code style, error-handling rules, CP0–CP4 workflow details, required tools (`context-retrieval`, `grok-search`, `codex`, `gemini`), RTK shell prefix, and Morph edit policy live in `rules/global-claude-workflow.mdc`.

## Common Commands

- Run skill tests: `./tests/claude-code/run-skill-tests.sh`
- Run integration tests: `./tests/claude-code/run-skill-tests.sh --integration`
- Run specific test: `./tests/claude-code/run-skill-tests.sh --test test-executing-plans.sh`
- Update plugin: `claude plugin update superpowers-ccg`
- Install MCPs: `claude mcp add codex ...` and `claude mcp add gemini ...` (see README.md)

## High-Level Architecture

Superpowers-CCG enhances Claude Code with CCG multi-model orchestration: Claude plans phases, routes execution, reviews outputs, and runs integration checks. Codex is the default executor for most implementation. Gemini handles UI, multimodal, and large-context visual/document phases.

Core workflow uses strict CP0 (context-retrieval context) → CP1 (phase routing) → CP2 (external execution) → CP3 (reconciliation if needed) → CP4 (phase review: `PASS`, `PASS_WITH_DEBT`, or `FAIL`) → integration checks after every phase.

Key areas:
- `skills/coordinating-multi-model-work/`: routing, checkpoints, CP protocol, external response format
- `skills/`: domain-specific skills (debugging-systematically, writing-plans, etc.)
- `tests/claude-code/`: bash-based skill behavior verification using headless `claude -p`

See README.md for full CCG details, model routing matrix, and differences from original superpowers. All changes must follow the checkpoint protocol in skills/coordinating-multi-model-work/SKILL.md.

## CP1 Trigger Table

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| Backend / Logic / API | Codex | No | Default implementation route |
| Tests / CI / Terminal / Infra-DevOps | Codex | No | Terminal-Bench leader |
| Large refactor (>=10 files or >1K LOC) | Codex | No | 7-hr horizon |
| Bug fix / Debugging / Performance | Codex | No | Snappy small + sustained deep |
| Data / ML / Analytics | Codex | No | Logic-heavy |
| UI components / CSS / animation / canvas / SVG | Gemini | No | WebDev Arena leader |
| Multimodal input -> code | Gemini | No | Only multimodal frontier |
| Large-context sweep (>200K tokens) | Gemini | No | 1M ctx, cheapest tier |
| Visual regression / screen automation / OCR | Gemini | No | ScreenSpot-Pro 72.7% |
| Doc / spec extraction from PDFs / diagrams | Gemini | No | Document understanding |
| Security / compliance / legal-sensitive code | Codex | No (mandatory Claude review gate) | Hallucination guardrail |
| Architecture conflict / multi-domain | Cross-Validation (Codex + Gemini) | Yes | Rare arbitration |
| Docs / Comments / Coordination / Simple edits | Claude | No | Per user constraint |
| Orchestration / Review / Integration / Planning | Claude | No | Per user constraint |
| Uncategorized / Ambiguous | Claude | No | Fail-closed; clarify |

Tiebreakers and new routing axes are canonical in `skills/coordinating-multi-model-work/routing-decision.md` under `## Tiebreaker Order` and `## New Routing Axes`.
