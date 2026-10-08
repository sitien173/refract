---
name: using-superpowers
description: "Use at the start of every conversation, before the first reply, clarifying question, or tool call. Matches the request to the skills that apply and decides whether the work is direct or coordinated."
---

# Using Superpowers

## Role

You route every request to its skills before acting. This file is also the
single source of truth for coordination scope.

## Precedence

1. User instructions: direct requests, CLAUDE.md, AGENTS.md, GEMINI.md.
2. Skills.
3. Default behavior.

Skip a skill workflow only when the user explicitly says to.

## Workflow

1. **Match.** Before any response, clarifying question, file read, or command,
   scan the available skills. Invoke each skill whose description matches the
   request, and every skill the user names.
2. **Order.** Process skills run first and set the approach. Implementation
   skills carry it out.
   - "Let's build X" → `superpowers-ccg:brainstorming`, then implementation skills.
   - "Fix this bug" → `superpowers-ccg:systematic-debugging`, then domain skills.
   - Before plan mode on coordinated work, run `brainstorming` unless a
     confirmed design already exists.
3. **Announce.** Say "Using <skill> to <purpose>."
4. **Classify scope** with the rule below and emit the scope line.
5. **Follow** the skill exactly. If on reading it does not fit, state why in
   one line and drop it.

## Scope Decision

Emit one line before acting:

```text
Scope: direct | coordinated - <deciding signal>
```

The work is **coordinated** when any risk signal is present, whatever its size:

- it spans multiple phases or components,
- it carries real correctness, security, data-loss, or migration risk,
- it needs a design decision,
- the user asks for a plan.

Otherwise it is **direct**. Typical direct work:

- a single-file or trivially scoped edit,
- documentation, comments, config, or formatting,
- a rename, string change, dependency bump, or one-line fix,
- anything the user asks you to just do directly.

A risk signal outranks these examples. A one-line auth check or a major-version
bump is coordinated. When the signal is genuinely ambiguous, ask one bounded
question: direct or planned.

Direct work uses your own tools and skips all three gates. Process skills such
as `systematic-debugging`, `test-driven-development`, and
`verifying-before-completion` still apply. Coordinated work loads
`coordinating-multi-model-work`.
