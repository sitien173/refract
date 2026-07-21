---
name: brainstorming
description: "Clarifies intent, requirements, constraints, and trade-offs before implementation planning. Use for new features, behavior changes, ideation, or incomplete specifications."
---

# Brainstorming Ideas Into Designs

Load `coordinating-multi-model-work` first. This skill owns design dialogue only;
the coordinating skill owns OpenMCP selection and consultation mechanics.

## Workflow

1. Inspect the minimum relevant project context: docs, files, and recent changes.
2. Ask one question at a time; prefer bounded choices when useful.
3. Clarify purpose, users, constraints, non-goals, success criteria, and risks.
4. For non-trivial design, request one focused consultation through Gate 1 and
   reconcile its advice with the user's requirements. Skip only fully specified,
   low-risk routine work.
5. Present two or three viable approaches with trade-offs and a recommendation.
6. Develop the selected design in short sections and confirm each section.
7. Cover architecture, components, data flow, errors, migration, and testing as
   applicable.
8. Write the confirmed design document, then offer `writing-plans`.

## Rules

- User requirements override consultation.
- Do not plan implementation before the design is confirmed.
- Do not ask multiple clarification questions in one message.
- Do not implement or commit unless the user explicitly changes scope.

## Reference

- `skills/coordinating-multi-model-work/SKILL.md` — consultation policy and job mechanics.
