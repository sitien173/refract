# Codex Base Prompt Templates

> Invoke via `mcp__codex__codex`.
> All prompts in English.

## Bounded Implementation Template

```text
## Task
{task_description}

## Files
{file_list}

## Acceptance
{acceptance_criteria}

## Verify
{verify_command}

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: Return exactly one of:
1. ## DIFF → ## VERIFY → ## ISSUES
2. ## QUESTIONS
```

## Narrow Analysis Template

```text
## Question
{narrow_question}

## Files
{file_list}

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: Output ## ANALYSIS (<=120 words) → ## ISSUES (<=3) → ## VERDICT (one line).
```
