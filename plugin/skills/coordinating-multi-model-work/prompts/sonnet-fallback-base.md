# Sonnet Fallback Prompt Template

> Invoke via `Agent` tool with `model: "sonnet"`.
> Used only when Codex/Gemini MCP is unavailable after 2 retries.
> Subagent edits files directly using Edit/Write/Bash tools.

## Bounded Implementation Template

```text
## Original User Request
{compressed_user_request}

## Task Context Bundle
TASK_ID: {task_id}

## Context Refs
{context_refs}

## Hydrated Context
{hydrated_context}

## CP1 Task Summary
{task_summary}

## Files
{file_list}

## Success Criteria
{success_criteria}

## Verify
{verify_command}

## Instructions
You are a fallback implementation worker. Codex/Gemini MCP tools were unavailable, so you are implementing this task directly.

Rules:
- Read each file before editing it.
- Use the Edit tool for targeted changes, Write tool for new files.
- Run the verify command via Bash when done.
- Report what you changed and whether the verify command passed.
- Do not create documentation, tests, or refactors beyond what the success criteria require.
- Do not add comments, type annotations, or error handling beyond scope.
```
