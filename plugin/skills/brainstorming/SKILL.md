---
name: brainstorming
description: "Use when the user wants to build, add, or change something and the approach is not settled, even if they only describe a problem or a rough idea. Clarifies intent, constraints, and trade-offs into a confirmed design document before any plan or code. Not for a known bug or a fully specified small edit."
---

# Brainstorming Ideas Into Designs

## Role

This skill owns design dialogue. Load `coordinating-multi-model-work` first; it
owns OpenMCP mechanics, Git anchors, and the plan slug. `writing-plans` owns
implementation planning.

## Constraints

- User requirements override consultation advice.
- Ask one question per message. Offer two to four bounded choices when the
  answer space allows it.
- Produce design only. Product code, plans, and task lists belong to later
  skills.
- Apply YAGNI: cut every feature the confirmed purpose does not need.

## Workflow

Each step ends on its stated completion criterion.

1. **Context.** Read only files that bear on the request. Done when you can
   name every component the idea touches.
2. **Clarify.** Resolve purpose, users, constraints, non-goals, success
   criteria, and risks. Done when each has a user-confirmed answer or an
   explicit `n/a`.
3. **Consult.** For non-trivial design, request one focused Gate 1
   consultation through the Coordinator. Non-trivial means any of: a new
   component, a cross-component change, a data or API contract change, a
   security impact, or two defensible approaches. Skip it for fully specified,
   low-risk routine work. When consultation is unavailable or fails, continue
   and record the reason in the design.
4. **Approaches.** Present two or three viable approaches with trade-offs and a
   recommendation. Where consultation conflicts with the user, show both. Done
   when the user selects one.
5. **Design.** Develop the selected approach in short sections: architecture,
   data flow, errors, migration, and testing, as applicable. Confirm each
   section before the next. When an answer invalidates an earlier section,
   revisit that section first.
6. **Write.** Propose a slug and confirm it. The Coordinator sets the plan
   `base` anchor at a clean root. Then write `docs/plans/<slug>/DESIGN.md` in
   the format below.
7. **Approve.** Ask for explicit approval of the whole document. Done when the
   user approves. Then offer `writing-plans`.

## Edge Cases

- **Direct scope.** The request is direct under `using-superpowers`: say so and
  leave this skill.
- **Design waived.** The user wants to skip design: confirm once, write a
  `DESIGN.md` whose status is `Waived by user`, and offer `writing-plans`.
- **Existing plan.** `docs/plans/<slug>/` already exists: ask whether to revise
  it or pick a new slug. Keep the existing files until the user decides.
- **Dialogue abandoned.** The user stops answering: summarize confirmed and
  open items in chat and write no file.

## Output Format

```markdown
# <Topic> Design

**Status:** Confirmed <YYYY-MM-DD> | Waived by user
**Consultation:** <one-line outcome> | skipped - <reason>

## Purpose
## Users and Success Criteria
## Constraints and Non-Goals
## Chosen Approach
<approach; one line per rejected alternative with its reason>
## Architecture and Data Flow
## Errors and Edge Cases
## Migration
## Testing
## Risks and Open Questions
```

Mark an inapplicable section `n/a` rather than deleting it.
