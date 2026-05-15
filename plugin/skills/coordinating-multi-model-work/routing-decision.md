# CP1 Routing Decision Framework

## Contents

- Overview
- When to Use
- Phase Assessment Steps
- Decision Output
- Routing Targets
- Session Policy
- New Routing Axes
- Detailed Task Matrix
- Compact Routing Matrix
- Decision Guidelines
- Tiebreaker Order
- Example

## Overview

This framework defines CP1 Phase Assessment & Routing for multi-model execution.

## When to Use

Invoke this framework immediately after CP0 completes and before the first executor call for a phase.

Inputs:

- original user request
- CP0 context artifacts
- the inline CP1 routing matrices below

## Phase Assessment Steps

1. Read the original request and the CP0 context artifacts.
2. Summarize the active phase in one English sentence.
3. Check whether the phase is clear, sufficiently scoped, and contains 2-4 related tasks.
4. If unclear, route to `Claude`, output the CP1 decision block, and ask clarifying questions immediately.
5. Classify the task against the inline CP1 routing matrices below.
6. Decide model ownership, cross-validation, and `SESSION_POLICY`.
7. Build the next executor prompt tier:
   - Tier 1 for a fresh worker session
   - Tier 3 when continuing a related phase on the same worker session
8. Keep `HYDRATED_CONTEXT` under 300 tokens hard cap when preparing worker context.

## Decision Output

```text
# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the phase]

## Route
- Model: Gemini / Codex / Cross-Validation (Codex + Gemini) / Claude
- Cross-Validation: Yes / No
- Session-Policy: CONTINUE / FRESH
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

## Routing Targets

- `Codex` - Default implementation executor for backend, full-stack, tests, debugging, infrastructure, repo tooling, and most coding phases
- `Gemini` - UI-heavy executor for visual layout, styling, motion, canvas/SVG, and complex interactions
- `Cross-Validation (Codex + Gemini)` - Rare arbitration for unresolved architecture or true multi-domain uncertainty
- `Claude` - Orchestrator, reviewer, integrator, documentation editor, or clarification handler
- `Session-Policy` defaults to `FRESH`. Use `CONTINUE` only when the next phase stays with the same worker and the files or subsystem materially overlap.

## Session Policy

`SESSION_POLICY` decision table is canonical in `context-sharing.md`. Default is `FRESH`; use `CONTINUE` when same worker and overlapping files/subsystem.

## New Routing Axes

1. Context size — >200K tokens routes to Gemini (1M ctx, cost-optimal tier).
2. Multimodal input — screenshots, PDFs, video, design mocks route to Gemini (only true multimodal frontier).
3. Horizon length — >1 hr autonomous chain routes to Codex (validated 7+ hr sustained).

## Detailed Task Matrix

| Task Category | Examples | CP0 Context Tools | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- | --- | --- |
| Backend / Logic / API | API endpoints, business logic, DB, auth | stellaris | Codex | No | Default implementation route |
| Tests / CI / Terminal / Infra-DevOps | unit/integration/E2E tests, CI scripts, Docker, deploy scripts | stellaris | Codex | No | Terminal-Bench leader |
| Large refactor (>=10 files or >1K LOC) | multi-package refactor, migrations | stellaris | Codex | No | 7-hr horizon validated |
| Bug fix / Debugging / Performance | crashes, regressions, slow queries | stellaris | Codex | No | Snappy small + sustained deep |
| Data / ML / Analytics | pipelines, queries, simple ML | stellaris | Codex | No | Logic-heavy |
| UI components / CSS / animation / canvas / SVG | React/Vue components, Tailwind, motion | stellaris | Gemini | No | WebDev Arena leader |
| Multimodal input -> code | screenshot/PDF/video/mock to code | stellaris | Gemini | No | Only multimodal frontier |
| Large-context sweep (>200K tokens) | repo-wide analysis, long docs | stellaris | Gemini | No | 1M ctx, cheapest tier |
| Visual regression / screen automation / OCR | snapshot diffs, screen scraping | stellaris | Gemini | No | ScreenSpot-Pro 72.7% |
| Doc / spec extraction from PDFs / diagrams | requirement extraction | stellaris | Gemini | No | Document understanding |
| Security / compliance / legal-sensitive code | auth, encryption, PII | stellaris | Codex | No (mandatory Claude review gate) | Hallucination guardrail |
| Architecture conflict / true multi-domain | UI+BE+data design, risky migration | stellaris | Cross-Validation (Codex + Gemini) | Yes | Rare arbitration |
| Docs / Comments / Coordination / Simple edits | README, typo, config | stellaris | Claude | No | Per user constraint |
| Orchestration / Review / Integration / Planning | review, merge, plan | stellaris | Claude | No | Per user constraint |
| Uncategorized / Ambiguous | unclear or spans many areas | stellaris + Grok Search if external research needed | Claude | No | Fail-closed: ask clarifying questions |

## Decision Guidelines

- Default implementation route -> `Codex`
- UI-heavy phase where visual work dominates -> `Gemini`
- Unresolved architecture or true multi-domain uncertainty -> `Cross-Validation (Codex + Gemini)`
- Documentation-only, review, integration, or pure coordination -> `Claude`
- If the task is ambiguous or underspecified, fail closed to `Claude` and ask clarifying questions
- If multiple triggers fire, apply Tiebreaker Order section.

## Tiebreaker Order

1. Hallucination-sensitive (security/compliance/legal/medical) -> Codex + mandatory Claude review gate.
2. Multimodal input present -> Gemini.
3. Context >200K tokens -> Gemini.
4. UI-dominant phase -> Gemini.
5. Else -> Codex.

## Example

**Input:** "Fix the flaky test in CI pipeline"

**Output:**
```text
# CP1 ROUTING DECISION

## Task Summary
Fix the flaky CI pipeline test and restore reliable verification.

## Route
- Model: Codex
- Cross-Validation: No
- Session-Policy: FRESH
- Reason: CI/CD debugging is a backend and systems task with a single clear owner.

## Next Action
Proceed to CP2 with Codex.
```
