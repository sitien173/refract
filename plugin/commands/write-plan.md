---
name: write-plan
description: Create implementation plan with coarse phases of 2-4 related tasks
disable-model-invocation: true
---

# Write plan

## Usage

Invoke via `/superpowers-ccg:write-plan`

## Workflow

You MUST invoke both skills via the `Skill` tool in this order before any other action:

1. `Skill(superpowers-ccg:coordinating-multi-model-work)` — load canonical 3-gate workflow + routing + resume artifacts.
2. `Skill(superpowers-ccg:writing-plans)` — load plan-writing workflow.

Then follow the writing-plans skill exactly as presented. The resume check (step 1 of that skill) is mandatory — do not skip it even when the user names a fresh topic.
