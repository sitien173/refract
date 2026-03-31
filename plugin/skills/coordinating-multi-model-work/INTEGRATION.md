# Multi-Model Integration Guide

Claude is orchestrator-only. All implementation code goes through external models.

## Standard Pattern

1. Define one bounded task.
2. Include only the minimum context needed to complete that task.
3. Ask the worker for one of two outcomes:
   - changed hunks / patch-ready diff
   - blocking questions
4. Reuse `SESSION_ID` only for follow-up fixes on the same task.
5. Run Opus review on the resulting artifact.

## Hard Rules

- Do not ask for draft code that the orchestrator will later re-implement.
- Do not ask for design prose on an implementation task.
- Do not restate the whole PRD, plan, or prior conversation in every prompt.
- Do not send multiple workers the same bounded implementation task.

## Prompt Structure

Every implementation prompt should contain:

```text
## Task
[single bounded task]

## Files
[explicit file set]

## Acceptance
[2-5 concrete checks]

## Verify
[exact command]

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: Output only one of:
1. ## DIFF → ## VERIFY → ## ISSUES
2. ## QUESTIONS
```

## When To Cross-Validate

Use `CROSS_VALIDATION` only for design arbitration or unresolved multi-domain ambiguity. When you do:
- ask both models the same narrow question
- compare only divergences
- do not ask both to generate full implementations
