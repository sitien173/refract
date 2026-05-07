# Smart Routing Optimization — Design

Date: 2026-05-07
Owner: Claude (orchestrator)
Status: Design (pre-implementation)

## Goal

Optimize CP1 routing to exploit each model's 2026 strength profile. Claude stays orchestrator/docs/simple-edits only — never executor for non-trivial code.

## Model Strength Profile (April 2026 benchmarks)

### Claude Opus 4.7 (orchestrator/docs only)
- SWE-bench Verified 87.6%, SWE-bench Pro 64.3%, MCP-Atlas 77.3% (best tool use), OSWorld 78%
- Strength: hard fixes, review-quality reasoning, agentic tool calling, sustained coding
- Weakness vs role: expensive ($5/$25 per M); long-context retrieval regression vs Opus 4.6
- Per user constraint: NOT used as executor. Used for orchestration, review, integration, docs, comments, simple coordination edits.

### GPT-5.5-Codex (default executor)
- Terminal-Bench 2.0 82.7% (leader), SWE-bench Verified 74.5%, Code-Refactor 51.3%
- Strength: 7+ hr autonomous runs, AGENTS.md adherence, terminal/CLI work, large refactors, token-efficient adaptive reasoning, snappy on small tasks
- Weakness: 86% AA-Omniscience hallucination rate disqualifies raw use for legal/medical/compliance — requires Claude review gate

### Gemini 3.1 Pro (specialist executor)
- WebDev Arena 1487 Elo (leader), ScreenSpot-Pro 72.7%, ARC-AGI-2 31.1%, 1M context
- Strength: UI/web dev, multimodal (video/PDF/screenshot/mock), large-context sweeps, document understanding, visual reasoning
- Weakness: 10-15s latency, thought-signature API complexity, price doubles >200K ($4/$18)

## New Routing Axes (added)

1. **Context size** — >200K tokens → Gemini (1M ctx, cost-optimal)
2. **Multimodal input** — screenshots, PDFs, video, design mocks → Gemini (only true multimodal frontier)
3. **Horizon length** — >1 hr autonomous chain → Codex (validated 7+ hr sustained)

Old "UI dominates" trigger broadened. Real Gemini wedge = visual + long-context + multimodal.

## Revised Routing Matrix

| Trigger | Model | Cross-Val | Notes |
|---|---|---|---|
| Backend, API, business logic, DB | Codex | No | Default |
| Tests, CI, terminal scripts, infra/DevOps | Codex | No | Terminal-Bench leader |
| Large refactor (>=10 files or >1K LOC) | Codex | No | Refactor-bench + 7-hr horizon |
| Bug fix, debugging, performance | Codex | No | Snappy small + sustained deep |
| Data/ML/analytics pipelines | Codex | No | Logic-heavy |
| UI components, CSS, animation, canvas/SVG | Gemini | No | WebDev Arena leader |
| Multimodal input → code (screenshot/PDF/video/mock) | Gemini | No | Only multimodal frontier |
| Large-context sweep (>200K tokens) | Gemini | No | 1M ctx, cheapest tier |
| Visual regression, screen automation, OCR | Gemini | No | ScreenSpot-Pro 72.7% |
| Doc/spec extraction from PDFs/diagrams | Gemini | No | Document understanding |
| Security/compliance/legal-sensitive code | Codex | No (mandatory Claude review gate) | Hallucination guardrail |
| Architecture conflict, true multi-domain uncertainty | Cross-Validation (Codex+Gemini) | Yes | Rare arbitration |
| Docs, comments, coordination, simple edits | Claude | No | Per user constraint |
| Orchestration, review, integration, planning | Claude | No | Per user constraint |
| Ambiguous / underspecified | Claude | No | Fail-closed; clarify |

## Tiebreaker Order (multiple triggers fire)

1. Hallucination-sensitive (security/compliance/legal/medical) → Codex + mandatory Claude review
2. Multimodal input present → Gemini
3. Context >200K tokens → Gemini
4. UI-dominant phase → Gemini
5. Else → Codex

## Session Policy

| Condition | Policy |
|---|---|
| Same worker + overlapping files/subsystem | CONTINUE |
| Same worker + adjacent phase, no file overlap | FRESH |
| Switch worker (Codex↔Gemini) | FRESH always |
| Long-horizon Codex run active (>1hr) | CONTINUE until phase complete |
| Multimodal artifact carryover (Gemini parsed PDF reused next phase) | CONTINUE |
| Prior phase FAIL after 2 Tier-2 retries | FRESH |

## Cross-Validation Triggers (tightened)

Use only when:
- Unresolved architecture spanning UI + backend + data
- Conflicting prior ERP outputs across phases
- User-flagged high-risk migration

NOT for routine full-stack work — Codex handles solo.

## Failure Rules (unchanged)

Codex/Gemini MCP error (timeout, session-failed, permission-blocked, tool-unavailable, model-error) → output `BLOCKED`. No retry. No executor switch.

## Prompt Tier Budget (unchanged)

- Tier 1 initial: <=1500 tokens
- Tier 2 same-phase follow-up: <=400 tokens
- Tier 3 cross-phase continuation: <=600 tokens
- HYDRATED_CONTEXT hard cap: <=300 tokens

## Files To Update (implementation phase)

- `skills/coordinating-multi-model-work/routing-decision.md` — replace Detailed + Compact matrices, add tiebreaker section, add new axes
- `skills/coordinating-multi-model-work/SKILL.md` — update routing summary if present
- `CLAUDE.md` (root) — update Trigger Table to mirror new matrix
- `rules/global-claude-workflow.mdc` — sync routing guide if it duplicates matrix
- Hook reminder text in `.claude/settings*.json` if it embeds routing matrix verbatim

## Acceptance Criteria

- New matrix covers context-size + multimodal + horizon axes
- Tiebreaker order explicit and ordered
- Claude never appears as executor for non-trivial code paths
- Hallucination-sensitive paths have mandatory Claude review gate
- Cross-Validation triggers narrowed to true arbitration cases
- All references in repo updated consistently

## Sources

- [Best AI for Coding 2026 — MorphLLM](https://www.morphllm.com/best-ai-model-for-coding)
- [Opus 4.7 vs Gemini 3.1 vs GPT-5.5 — Sagnik Bhattacharya](https://sagnikbhattacharya.com/blog/chatgpt-5-5-vs-claude-opus-4-7-vs-gemini-3-1-pro)
- [Gemini 3.1 Pro vs Opus 4.7 vs GPT-5.5 — Spectrum AI Lab](https://spectrumailab.com/blog/gemini-3-1-pro-vs-claude-opus-4-7-vs-gpt-5-5-decision-framework-2026)
- [Opus 4.7 Benchmarks — Vellum](https://www.vellum.ai/blog/claude-opus-4-7-benchmarks-explained)
- [Gemini 3 Developer Guide — Google](https://ai.google.dev/gemini-api/docs/gemini-3)
- [Introducing GPT-5.3-Codex — OpenAI](https://openai.com/index/introducing-gpt-5-3-codex/)
- [GPT-5.5-Codex Benchmark — CodeRabbit](https://www.coderabbit.ai/blog/gpt-5-5-benchmark-results)
