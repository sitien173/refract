---
name: brainstorming
description: "Explores intent, requirements, trade-offs, and design via dialogue before planning. Use for new features, components, behaviour changes, ideation, or spec design."
---

# Brainstorming Ideas Into Designs

## Use When

- Idea is not yet a complete spec.
- User asks for design, requirements, ideation, or planning.
- Trade-offs, constraints, or success criteria need clarifying.

## Workflow

1. **Cross-validate first.** New feature / ideation / proposal → invoke `coordinating-multi-model-work` Plan gate to run Cross-Validation (Codex + Gemini narrow question). Reconcile divergences before clarification.
2. Inspect current project state: relevant files, docs, recent commits.
3. Ask one question at a time; prefer multiple choice when useful.
4. Clarify purpose, constraints, non-goals, success criteria, preferences.
5. Propose 2–3 approaches with trade-offs; lead with the recommended option.
6. Present the design in 200–300 word sections; confirm each before continuing.
7. Cover architecture, components, data flow, error handling, testing.
8. After confirmation, save `docs/plans/YYYY-MM-DD-<topic>-design.md` and report the path.
9. Offer to turn the design into an implementation plan via `writing-plans`.

## Hard Rules

- Cross-Validation before design exploration for new features unless user says "skip cross-validation".
- One question per message during clarification.
- Always write the final confirmed design document.
- Commit only if user asks.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
