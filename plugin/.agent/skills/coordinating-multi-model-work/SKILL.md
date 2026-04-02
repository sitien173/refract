---
name: coordinating-multi-model-work
description: Route bounded implementation tasks to Codex or Gemini while keeping Cursor out of the implementation hot path. Use for coding, refactors, debugging, UI work, APIs, databases, scripts, and CI/CD changes.
---

# Coordinating Multi-Model Work

## Routing

- `codex`: backend APIs, databases, auth, scripts, CI/CD, Docker, infrastructure, repo tooling
- `gemini`: UI components, layouts, styling, interaction polish
- `cross-validation`: architectural disputes or genuinely ambiguous ownership

## Rules

1. Reduce the current work to one bounded task.
2. Assign exactly one worker unless architecture uncertainty makes that unsafe.
3. Include the file set, acceptance criteria, and verification command.
4. Require one of two outputs only:
   - a patch-ready diff
   - blocking questions
5. Reuse the same worker context for fixes on the same task.

## Anti-patterns

- Do not ask for a prototype and then rewrite it yourself.
- Do not route the same bounded task to multiple workers by default.
- Do not let review steps replay the entire execution history.
- Do not keep long planning and execution narration in the main Cursor thread.
