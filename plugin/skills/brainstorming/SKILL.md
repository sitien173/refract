---
name: brainstorming
description: "Explores user intent, requirements, and design through collaborative dialogue before implementation. Use when creating features, building components, adding functionality, modifying behavior, designing specs, ideating, or planning creative work."
---

# Brainstorming Ideas Into Designs

## Use When

- User has an idea but not a complete spec.
- User asks for design, requirements, ideation, or planning before implementation.
- Task needs current project context, trade-offs, or success criteria clarified.

## Workflow

1. Inspect current project state first: relevant files, docs, recent commits, and Auggie context when the project area is broad.
2. Ask one question at a time; prefer multiple choice when useful.
3. Clarify purpose, constraints, non-goals, success criteria, and user preferences.
4. Propose 2-3 approaches with trade-offs; lead with the recommended option.
5. Present the design in 200-300 word sections and ask whether each section looks right so far.
6. Cover architecture, components, data flow, error handling, and testing.
7. After confirmation, create `docs/plans/YYYY-MM-DD-<topic>-design.md` and report the path.
8. Ask whether the user is ready to turn the design into an implementation plan.

## Hard Rules

- Follow `skills/shared/protocol-threshold.md` when routing toward implementation.
- One question per message during clarification.
- CP2 starts only after the design is routed into implementation.
- Do not skip writing the final confirmed design document.
- Only commit if the user explicitly asks.

## References

- `skills/shared/protocol-threshold.md` — CP0-CP4 gates for implementation routing.
- `skills/shared/supplementary-tools.md` — optional Auggie and Grok Search research guidance.
- `skills/shared/multi-model-integration-section.md` — multi-model validation when design work becomes implementation.
