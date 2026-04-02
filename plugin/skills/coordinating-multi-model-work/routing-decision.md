# CP1 Routing Decision Framework

## Overview

This framework defines CP1 Task Assessment & Routing for multi-model task distribution.

## When to Use

Invoke this framework immediately after CP0 completes and before the first Task call.

Inputs:

- original user request
- full `CONTEXT_PACKAGE` from CP0
- the inline CP1 routing matrices below

## Task Assessment Steps

1. Read the original request and the CP0 context package.
2. Summarize the core task in one English sentence.
3. Check whether the task is clear and sufficiently scoped.
4. If unclear, route to `Claude`, output the CP1 decision block, and ask clarifying questions immediately.
5. Classify the task against the inline CP1 routing matrices below.
6. Decide model ownership and cross-validation.

## Decision Output

```text
# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the request]

## Route
- Model: Gemini / Codex / Cross-Validation (Codex + Gemini) / Claude
- Cross-Validation: Yes / No
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

## Routing Targets

- `Codex` - Backend and systems expert for APIs, databases, algorithms, server-side logic, CI/CD, scripts, Dockerfiles, infrastructure, and repo tooling
- `Gemini` - Frontend expert for UI, components, styles, interactions
- `Cross-Validation (Codex + Gemini)` - Multiple models for full-stack tasks, architectural decisions, or high uncertainty
- `Claude` - Orchestrator only: routing decisions, coordination, documentation edits, or clarification handling

## Detailed Task Matrix

| Task Category | Examples | CP0 Context Tools | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- | --- | --- |
| Pure Frontend / UI / Styling | CSS, React/Vue components, Tailwind, animations | Hybrid (Auggie + Morph + Serena) | Gemini | No | Fastest path |
| Pure Backend / Logic / API | API endpoints, business logic, DB queries, auth | Hybrid (Auggie + Morph + Serena) | Codex | No | Use cross-validation only if the task becomes high-impact or architecture-heavy |
| Full-Stack / Architecture | New feature spanning FE + BE, major refactors | Hybrid (Auggie + Morph + Serena) | Cross-Validation (Codex + Gemini) | Yes | Both models run in parallel |
| Docs / Comments / Simple Fix | README updates, typo fixes, minor config | Auggie only (Serena optional) | Claude | No | Usually no external models |
| Debugging / Performance | Bug fixes, optimization, slow queries | Hybrid (Auggie + Morph + Serena) | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Docker, CI/CD, deployment scripts | Hybrid (Auggie + Morph + Serena) | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Data pipelines, queries, simple ML logic | Hybrid (Auggie + Morph + Serena) | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Unit tests, integration tests, E2E | Hybrid (Auggie + Morph + Serena) | Cross-Validation (Codex + Gemini) | Yes | Useful when tests span frontend and backend behavior |
| Cross-Cutting / Security | Auth, encryption, compliance, rate-limiting | Hybrid (Auggie + Morph + Serena) | Codex | Yes | Extra safety layer |
| Uncategorized / Ambiguous | Request unclear or spans many areas | Hybrid (Auggie + Morph + Serena + Grok Search if needed) | Claude | No | Fail-closed: ask clarifying questions immediately |

## Compact Routing Matrix

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| Pure Frontend / UI / Styling | Gemini | No | Fastest path |
| Pure Backend / Logic / API | Codex | No | Use cross-validation only if the task becomes high-impact or architecture-heavy |
| Full-Stack / Architecture | Cross-Validation (Codex + Gemini) | Yes | Both models run in parallel |
| Docs / Comments / Simple Fix | Claude | No | Usually no external models |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Cross-Validation (Codex + Gemini) | Yes | Useful when tests span frontend and backend behavior |
| Cross-Cutting / Security | Codex | Yes | Extra safety layer |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

## Decision Guidelines

- Strong backend or systems signals and weak/no frontend signals → `Codex`
- Strong frontend signals and weak/no backend signals → `Gemini`
- Strong signals in both domains or high uncertainty → `Cross-Validation (Codex + Gemini)`
- Documentation-only or pure coordination → `Claude`
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
