# CP2 Prompt Discipline — Token Optimization Plan

**Date:** 2026-04-11  
**Goal:** Prevent Claude from pre-writing implementation in HYDRATED_CONTEXT when building CP2 prompts for Codex/Gemini, reducing prompt bloat from ~3000+ tokens to ~150 tokens.

---

## Problem

When routing to Codex or Gemini, Claude fills `HYDRATED_CONTEXT` and `CP1 Task Summary` with pre-written file contents (full JSON, TOML, TypeScript, etc.). This:
- Wastes tokens — Codex/Gemini know standard patterns and don't need pre-written files
- Defeats the purpose of routing — Claude is doing the worker's job
- Creates prompts 10–20× larger than necessary

**Root cause:** No explicit constraint in the prompt templates forbids pre-written implementation in `HYDRATED_CONTEXT`.

---

## Success Criteria

- All three prompt templates (`codex-base.md`, `gemini-base.md`, `implementer-prompt.md`) contain a `## Prompt Discipline` block with explicit anti-pattern rules
- `context-sharing.md` contains a "do NOT" example showing pre-written file contents as an anti-pattern
- A lean scaffold CP2 prompt fits in ~150 tokens (file list + requirements + verify command)
- Existing tests still pass: `./tests/claude-code/run-skill-tests.sh`

---

## Tasks

### Task 1 — Add Prompt Discipline to `codex-base.md`

**File:** `skills/coordinating-multi-model-work/prompts/codex-base.md`

Add a `## Prompt Discipline` section immediately before the `## Bounded Implementation Template` block with these rules:

```markdown
## Prompt Discipline

Follow these rules when filling in the Bounded Implementation Template:

- `HYDRATED_CONTEXT` contains excerpts from **existing files only**. Never pre-write new file contents here.
- For greenfield or scaffold tasks with no relevant existing code: set `HYDRATED_CONTEXT` to the existing directory structure only (e.g. `ls` output), or omit it entirely.
- Keep `HYDRATED_CONTEXT` under ~300 tokens. Exceeding this means you are over-specifying.
- `{compressed_user_request}` is one or two sentences — the what and the constraint, not the how.
- `{task_summary}` is the CP1 Task Summary sentence verbatim — not a re-expanded spec.
- `{file_list}` is a flat list of file paths — not file contents.
- Let the worker decide implementation details. Codex knows standard patterns for common stacks.

**Anti-pattern (do not do this):**
```
## Hydrated Context
### package.json
{ "name": "my-app", "scripts": { "dev": "vite" }, ... full 40-line file ... }
### vite.config.ts
import { defineConfig } from "vite"; ... full file ...
```

**Correct pattern:**
```
## Hydrated Context
Existing directory: .git/, docs/ — do not modify.
No other files exist yet.
```
```

**Verify:** File contains `## Prompt Discipline` and `anti-pattern` keyword.

---

### Task 2 — Add Prompt Discipline to `gemini-base.md`

**File:** `skills/coordinating-multi-model-work/prompts/gemini-base.md`

Apply the identical `## Prompt Discipline` section as Task 1, inserted before `## Bounded Implementation Template`.

**Verify:** File contains `## Prompt Discipline` and `anti-pattern` keyword.

---

### Task 3 — Add Prompt Discipline to `implementer-prompt.md`

**File:** `skills/developing-with-subagents/implementer-prompt.md`

Add a `## Prompt Discipline` note inside the template block, after the `## Rules` section:

```markdown
    ## Prompt Discipline
    - HYDRATED_CONTEXT = excerpts from existing files only. Never pre-write new files here.
    - For scaffold/greenfield tasks: HYDRATED_CONTEXT = existing directory structure or empty.
    - Keep HYDRATED_CONTEXT under ~300 tokens.
    - File list = paths only, not contents.
    - Let the worker implement. Pre-writing defeats the purpose of routing.
```

**Verify:** File contains `Prompt Discipline` and `pre-writing defeats`.

---

### Task 4 — Add anti-pattern example to `context-sharing.md`

**File:** `skills/coordinating-multi-model-work/context-sharing.md`

Add a new `## Anti-Patterns` section at the end of the file:

```markdown
## Anti-Patterns

### Do NOT pre-write implementation in HYDRATED_CONTEXT

**Wrong** — pre-written file contents (this is the worker's job, not Claude's):
```text
HYDRATED_CONTEXT:
- package.json: { "name": "my-app", "scripts": { "dev": "vite" }, "dependencies": { ... } }
- vite.config.ts: import { defineConfig } from "vite"; export default defineConfig({ ... })
- tsconfig.json: { "compilerOptions": { "target": "ES2020", ... } }
```

**Correct** — existing code context only:
```text
HYDRATED_CONTEXT:
- Existing directory: .git/, docs/ — do not modify
- No source files exist yet
```

**Correct** — existing pattern reference for a modification task:
```text
HYDRATED_CONTEXT:
- src/api/auth.ts line 42: uses `withRetry(fn, 3)` pattern for all external calls
- Error type convention: throw `AppError` with `{ code, message, context }` shape
```
```

**Verify:** File contains `## Anti-Patterns` and `pre-written file contents`.

---

### Task 5 — Run existing tests

**Verify command:**
```bash
./tests/claude-code/run-skill-tests.sh
```

Confirm all tests pass, especially `test-cp2-external-execution-guards.sh` which validates CP2 prompt structure.

---

## Execution Order

1 → 2 → 3 → 4 (independent edits, can be done in any order)  
5 (run after all edits)

## Route

All tasks: **Claude** (docs-only edits, no external models needed)
