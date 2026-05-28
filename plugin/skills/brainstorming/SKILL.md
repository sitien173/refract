---
name: brainstorming
description: "Explores intent, requirements, trade-offs, and design via dialogue before planning. Use for new features, components, behaviour changes, ideation, or spec design."
---

# Brainstorming Ideas Into Designs

## Use When

- Idea not yet complete spec.
- User asks for design, requirements, ideation, or planning.
- Trade-offs, constraints, or success criteria need clarifying.

## Workflow

1. **Cross-validate only when warranted.** Run Cross-Validation (Codex + Gemini narrow question, reconcile divergences) **only** if the idea is full-stack, unclear, or high-impact per `coordinating-multi-model-work` CV triggers. Otherwise skip and proceed straight to clarification.
2. Inspect current project state: relevant files, docs, recent commits.
3. Ask one question at time; prefer multiple choice when useful.
4. Clarify purpose, constraints, non-goals, success criteria, preferences.
5. Propose 2–3 approaches with trade-offs; lead with recommended option.
6. Present design in 200–300 word sections; confirm each before continuing.
7. Cover architecture, components, data flow, error handling, testing.
8. After confirmation, save `docs/plans/YYYY-MM-DD-<topic>-design.md` and report path.
9. Offer to turn design into implementation plan via `writing-plans`.

## Hard Rules

- Cross-Validation only for full-stack / unclear / high-impact ideas; skip otherwise. User "skip cross-validation" override still wins when CV would otherwise trigger.
- One question per message during clarification.
- Always write final confirmed design document.
- Commit only if user asks.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.