# Codex Base Prompt Templates

> Invoke via `mcp__codex__codex`.
> All prompts in English.

## Prompt Discipline

Follow these rules when filling in the template below:

- `{hydrated_context}` contains excerpts from **existing files only**. Never pre-write new file contents here.
- For greenfield or scaffold tasks with no relevant existing code: set `{hydrated_context}` to the existing directory structure only (e.g. `ls` output), or omit it entirely.
- Keep `{hydrated_context}` under 800 tokens, preferably under 300 tokens. Exceeding this means you are over-specifying.
- Keep the total executor prompt context under 2500 tokens when practical.
- Same-phase follow-up prompts must send deltas only and stay under 1000 tokens when practical.
- `{compressed_user_request}` is one or two sentences — the what and the constraint, not the how.
- `{task_summary}` is the CP1 phase summary sentence verbatim — not a re-expanded spec.
- `{file_list}` is a flat list of file paths — not file contents.
- Let Codex decide implementation details. It knows standard patterns for common stacks.

**Anti-pattern (do not do this):**
```
## Hydrated Context
### package.json
{ "name": "my-app", "scripts": { "dev": "vite" }, "dependencies": { ... } }
### vite.config.ts
import { defineConfig } from "vite"; export default defineConfig({ ... })
```

**Correct — greenfield task:**
```
## Hydrated Context
Existing directory: .git/, docs/ — do not modify. No source files exist yet.
```

**Correct — modification task:**
```
## Hydrated Context
- src/api/auth.ts line 42: uses `withRetry(fn, 3)` pattern for all external calls
- Error convention: throw `AppError` with `{ code, message, context }` shape
```

## Phase Implementation Template

```text
## Original User Request
{compressed_user_request}

## Phase Context Bundle
TASK_ID: {task_id}

## Context Refs
{context_refs}

## Hydrated Context
{hydrated_context}

## CP1 Phase Summary
{task_summary}

## Files
{file_list}

## Success Criteria
{success_criteria}

## Reviewer Checklist
{reviewer_checklist}

## Integration Checks
{integration_checks}

## Response Protocol
Use exactly this structure:

# EXTERNAL RESPONSE PROTOCOL v1.1

## SUMMARY
One-sentence summary of what you did.

## FILES MODIFIED
| Action  | File Path          | Description of Change |
|---------|--------------------|-----------------------|
| Created | src/...            | ...                   |
| Edited  | src/...            | ...                   |

## FILE CONTENTS
For each file listed in FILES MODIFIED, return either:
1. the complete final file content (preferred), or
2. a unified diff patch if full content is impractical.

## CONTEXT ARTIFACTS
Optional reusable artifacts discovered or updated during execution.

## SPEC COMPLIANCE
- Meets Spec? YES / WITH_DEBT / NO
- Explanation: ...

## CLARIFICATIONS NEEDED
None (or list questions)

## NEXT STEPS / CONTINUATION
TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
```

## Narrow Analysis Template

```text
## Question
{narrow_question}

## Files
{file_list}

## Response Protocol
Output exactly: ## ANALYSIS (<=120 words) → ## ISSUES (<=3) → ## VERDICT (one line).
```
