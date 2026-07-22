---
name: brainstorming
description: "Clarifies intent, constraints, and trade-offs into a confirmed design before implementation planning."
---

# Brainstorming Ideas Into Designs

Load `coordinating-multi-model-work` first. This skill owns design dialogue, not
OpenMCP mechanics or implementation planning.

## Workflow

1. Inspect only the project context needed to understand the request.
2. Ask one question at a time; prefer bounded choices when useful.
3. Clarify purpose, users, constraints, non-goals, success criteria, and risks.
4. For non-trivial design, request one focused Gate 1 consultation and reconcile
   its advice with user requirements.
5. Present two or three viable approaches, their trade-offs, and a
   recommendation.
6. Develop the selected design in short sections; confirm each section.
7. Cover architecture, data flow, errors, migration, and testing as applicable.
8. Write the confirmed design, then offer `writing-plans`.

## Rules

- User requirements override consultation.
- Do not plan implementation before design confirmation.
- Do not ask multiple clarification questions at once.
- Do not implement product changes.
