# CP1 Routing Decision Framework

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
6. Decide model ownership and cross-validation.
7. Build one phase-scoped context bundle with `TASK_ID`, `CONTEXT_REFS`, and `HYDRATED_CONTEXT`.

## Decision Output

```text
# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the phase]

## Route
- Model: Gemini / Codex / Cross-Validation (Codex + Gemini) / Claude
- Cross-Validation: Yes / No
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

## Routing Targets

- `Codex` - Default implementation executor for backend, full-stack, tests, debugging, infrastructure, repo tooling, and most coding phases
- `Gemini` - UI-heavy executor for visual layout, styling, motion, canvas/SVG, and complex interactions
- `Cross-Validation (Codex + Gemini)` - Rare arbitration for unresolved architecture or true multi-domain uncertainty
- `Claude` - Orchestrator, reviewer, integrator, documentation editor, or clarification handler

## Detailed Task Matrix

| Task Category | Examples | CP0 Context Tools | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- | --- | --- |
| UI-heavy visual implementation | CSS, React/Vue components, Tailwind, animations, canvas/SVG, interactions | Auggie | Gemini | No | Use only when UI dominates the phase |
| Backend / Logic / API | API endpoints, business logic, DB queries, auth | Auggie | Codex | No | Default implementation route |
| Full-Stack / Architecture | New feature spanning FE + BE, major refactors | Auggie | Codex | No | Cross-validate only for unresolved architecture conflict |
| Docs / Comments / Coordination | README updates, typo fixes, minor config, workflow edits | Auggie | Claude | No | Usually no external executor |
| Debugging / Performance | Bug fixes, optimization, slow queries | Auggie | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Docker, CI/CD, deployment scripts | Auggie | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Data pipelines, queries, simple ML logic | Auggie | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Unit tests, integration tests, E2E | Auggie | Codex | No | Gemini only for visual/UI-heavy tests |
| Cross-Cutting / Security | Auth, encryption, compliance, rate-limiting | Auggie | Codex | No | Add Claude/human review instead of default cross-validation |
| Uncategorized / Ambiguous | Request unclear or spans many areas | Auggie + Grok Search if needed | Claude | No | Fail-closed: ask clarifying questions immediately |

## Compact Routing Matrix

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| UI-heavy visual implementation | Gemini | No | Use only when UI dominates the phase |
| Backend / Logic / API | Codex | No | Default implementation route |
| Full-Stack / Architecture | Codex | No | Cross-validate only for unresolved architecture conflict |
| Docs / Comments / Coordination | Claude | No | Usually no external executor |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Codex | No | Gemini only for visual/UI-heavy tests |
| Cross-Cutting / Security | Codex | No | Add Claude/human review instead of default cross-validation |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

## Decision Guidelines

- Default implementation route → `Codex`
- UI-heavy phase where visual work dominates → `Gemini`
- Unresolved architecture or true multi-domain uncertainty → `Cross-Validation (Codex + Gemini)`
- Documentation-only, review, integration, or pure coordination → `Claude`
- If the task is ambiguous or underspecified, fail closed to `Claude` and ask clarifying questions

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
- Reason: CI/CD debugging is a backend and systems task with a single clear owner.

## Next Action
Proceed to CP2 with Codex.
```
