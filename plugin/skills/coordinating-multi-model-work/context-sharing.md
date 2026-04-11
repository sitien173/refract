# Smart Context Sharing

This workflow uses orchestrator-managed smart context sharing to keep worker prompts narrow without losing important information.

## Core Model

1. CP0 uses Auggie to retrieve the minimum local code context needed for routing.
2. The orchestrator stores the useful output as small reusable `CONTEXT_ARTIFACTS`.
3. CP1 builds one `TASK_CONTEXT_BUNDLE` for the next bounded task.
4. CP2 sends only the task-scoped bundle:
   - compressed original request
   - `TASK_ID`
   - `CONTEXT_REFS`
   - `HYDRATED_CONTEXT`
   - explicit files
   - success criteria
   - verify command
5. If the same worker session continues on the same task, send deltas only.

## Artifact Guidelines

Good artifact ids are short, stable, and reusable:

- `req/core`
- `req/non_goals`
- `files/hotspots`
- `files/owners`
- `verify/command`
- `research/notes`
- `debug/root_cause`

Each artifact should contain one focused piece of information, not a narrative dump.

## Task Context Bundle

Every bounded task should get a bundle like:

```text
TASK_ID: task_042

CONTEXT_REFS:
- req/core
- files/hotspots
- verify/command

HYDRATED_CONTEXT:
- [short snippet from req/core]
- [short snippet from files/hotspots]
- [short snippet from verify/command]
```

## Delta Follow-Ups

When reusing the same worker `SESSION_ID` on the same task, do not resend the whole bundle. Send only:

- changed refs
- new hydrated snippets
- updated verify output
- current spec gaps

## Worker Output

Workers still return External Response Protocol v1.1, but they may also emit:

```text
## CONTEXT ARTIFACTS
- id: debug/root_cause
  summary: Race condition in token refresh before assertion
```

These artifacts can then be reused by later tasks instead of rediscovering the same information.

## Anti-Patterns

### Do NOT pre-write implementation in HYDRATED_CONTEXT

`HYDRATED_CONTEXT` is for existing code context only. Pre-writing new file contents here is the worker's job — doing it inflates prompts 10–20× with no benefit.

**Wrong** — pre-written file contents:
```text
HYDRATED_CONTEXT:
- package.json: { "name": "my-app", "scripts": { "dev": "vite" }, "dependencies": { ... full 40-line file ... } }
- vite.config.ts: import { defineConfig } from "vite"; export default defineConfig({ ... full file ... })
- tsconfig.json: { "compilerOptions": { "target": "ES2020", ... full file ... } }
```

**Correct** — greenfield task, no existing code:
```text
HYDRATED_CONTEXT:
- Existing directory: .git/, docs/ — do not modify
- No source files exist yet
```

**Correct** — modification task, existing patterns:
```text
HYDRATED_CONTEXT:
- src/api/auth.ts line 42: uses `withRetry(fn, 3)` pattern for all external calls
- Error type convention: throw `AppError` with `{ code, message, context }` shape
```

Keep `HYDRATED_CONTEXT` under ~300 tokens. If you are over that, you are over-specifying.
