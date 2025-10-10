---
name: Executing Plans
description: Execute detailed plans with mode-switching for review, execution, and handling blockers
when_to_use: When have a complete implementation plan to execute. When implementing in separate session from planning. When your human partner points you to a plan file to implement. When hit a blocker during execution. When plan needs re-review after updates.
version: 3.0.0
---

# Executing Plans

## Overview

Execute implementation plans by switching between reviewing, executing, and handling blockers based on current needs.

**Core principle:** Review critically, execute in batches, stop when blocked, report at checkpoints.

**Announce at start:** "I'm using the Executing Plans skill to implement this plan."

## Operating Modes

```dot
digraph executing_modes {
    rankdir=LR;
    node [shape=box, style=rounded];

    REVIEWING [label="REVIEWING Mode\n\nRead plan critically\nIdentify concerns/questions/gaps\nConsider skills/architecture/tracing-knowledge-lineages\nCreate TodoWrite if plan is sound"];

    EXECUTING [label="EXECUTING Mode\n\nWork through batch (default 3 tasks)\nFollow each step exactly\nRun all verifications\nMark tasks completed"];

    BLOCKED [label="BLOCKED Mode\n\nStop execution immediately\nIdentify specific blocker\nAsk for clarification/help"];

    REPORTING [label="REPORTING Mode\n\nShow what was implemented\nShow verification output\nSay 'Ready for feedback'"];

    REVIEWING -> EXECUTING [label="Plan is sound, no concerns\n(created TodoWrite, ready to start first batch)"];

    REVIEWING -> BLOCKED [label="Plan has critical gaps\n(missing information, unclear instructions, unmet dependencies)"];

    EXECUTING -> BLOCKED [label="Cannot proceed with current task\n(dependency missing, test failing, instruction unclear)"];

    EXECUTING -> REPORTING [label="Batch completed successfully\n(all tasks done, verifications pass)"];

    BLOCKED -> REVIEWING [label="Blocker resolved with plan update\n(partner updated plan, need to re-review changes)"];

    BLOCKED -> EXECUTING [label="Blocker resolved, can continue\n(got clarification, continue current batch)"];

    REPORTING -> EXECUTING [label="Feedback received, continue\n(no fundamental issues, execute next batch)"];

    REPORTING -> REVIEWING [label="Feedback requires plan changes\n(approach needs rethinking, plan being updated)"];
}
```

## Mode Switching Rules

**YOU MUST announce every mode switch:** "Switching to [MODE] mode because [reason]"

**No exceptions:**
- Not silent switches
- Not implied mode changes
- Every switch requires explicit announcement

## Red Flags - You're Forcing Through

- Hit a blocker but continue executing anyway
- Plan has concerns but you start executing
- Tests fail but you mark task completed
- Unclear instruction but you guess instead of asking
- Partner updating plan but you don't switch to REVIEWING

**All of these mean: STOP. Switch to appropriate mode (and announce it).**

## After All Tasks Complete

When all tasks are done and verified:
- Announce: "I'm using the Finishing a Development Branch skill to complete this work."
- Switch to skills/collaboration/finishing-a-development-branch
- Follow that skill to verify tests, present options, execute choice

## Remember

- Modes are operational stances, not rigid steps
- You can switch freely based on what's needed
- Always announce mode switches
- Blockers require immediate BLOCKED mode
- Never force through when stuck
