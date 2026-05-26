---
name: write-plan
description: Turn a confirmed design into a phase-based implementation plan
disable-model-invocation: true
---

# Write plan

## Usage

Invoke via `/superpowers-ccg:write-plan`

## Workflow

You MUST invoke both skills via the `Skill` tool in this order before any other action:

1. `Skill(superpowers-ccg:coordinating-multi-model-work)` — canonical 3-gate workflow + routing + resume artifacts.
2. `Skill(superpowers-ccg:writing-plans)` — phase-plan authoring workflow.

Then follow the writing-plans skill exactly as presented. Resume check (Step 1) is mandatory — never start a fresh plan if an `ACTIVE` handover already covers the topic.
