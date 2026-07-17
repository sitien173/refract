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

1. **Consult the configured advisor.** Use `task_route` to select its nickname
   and `execution_role`. Ask one narrow question for every non-trivial design.
   Skip only fully specified, low-risk routine work.
2. Inspect current project state: relevant files, docs, recent commits.
3. Ask one question at time; prefer multiple choice when useful.
4. Clarify purpose, constraints, non-goals, success criteria, preferences.
5. Propose 2–3 approaches with trade-offs; lead with recommended option.
6. Present design in 200–300 word sections; confirm each before continuing.
7. Cover architecture, components, data flow, error handling, testing.
8. Offer to turn the resulting design into an implementation plan via `writing-plans`.

## Hard Rules

- Configured consultation is mandatory for the non-trivial work defined in
  `coordinating-multi-model-work` Gate 1. User overrides always win.
- One question per message during clarification.
- Always write final confirmed design document.
- Commit only if user asks.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
