---
name: execute-plan
description: Execute plan one phase at a time with review and integration checkpoints
disable-model-invocation: true
---

# Execute plan

## Usage

Invoke via `/superpowers-ccg:execute-plan`

## Workflow

You MUST invoke both skills via the `Skill` tool in this order before any other action:

1. `Skill(superpowers-ccg:coordinating-multi-model-work)` — load canonical 3-gate workflow + routing + resume artifacts.
2. `Skill(superpowers-ccg:executing-plans)` — load phase-execution workflow.

Then follow the executing-plans skill exactly as presented. Step 3 (load resume artifacts) is mandatory for folder-layout plans — read `.handover.md` + every file in `read_first` BEFORE running the Plan gate.