---
name: developing-with-subagents
description: "Executes plans by dispatching fresh subagent per task with two-stage review (spec then quality). Use when: executing implementation plans in current session with independent tasks. Keywords: subagent, task execution, fresh context, iterative development"
---

# Subagent-Driven Development

## Contents

- [Overview](#overview)
- [When to Use](#when-to-use)
- [The Process](#the-process)
- [Checkpoint Integration](#checkpoint-integration)
- [Related Skills](#related-skills)

## Overview

Execute plan by routing each task to the appropriate external model (Codex/Gemini/Cursor based on domain), with two-stage review after each: spec compliance review first (Opus), then code quality review (deterministic: Cursor reviews Codex/Gemini work, Opus reviews Cursor work).

**Core principle:** Route to external model per task + two-stage review (spec via Opus, then quality via deterministic reviewer) = high quality, fast iteration. Claude orchestrates but never implements.

## Protocol Threshold (Required)

Follow the [CP Protocol Threshold] injected by hooks:

- Before the first Task call: output a standalone [CP1 Assessment] block (the block itself must not include tool calls; tool calls may follow in the same reply)
- Before claiming completion / requesting review / claiming verification passed: output a standalone [CP3 Assessment] block (the block itself must not include tool calls; the claim may follow in the same reply)

If unmet -> immediately perform the CP assessment, then continue the flow right away; do not stop or interrupt.

## When to Use

```dot
digraph when_to_use {
    "Have implementation plan?" [shape=diamond];
    "Tasks mostly independent?" [shape=diamond];
    "Stay in this session?" [shape=diamond];
    "developing-with-subagents" [shape=box];
    "executing-plans" [shape=box];
    "Manual execution or brainstorm first" [shape=box];

    "Have implementation plan?" -> "Tasks mostly independent?" [label="yes"];
    "Have implementation plan?" -> "Manual execution or brainstorm first" [label="no"];
    "Tasks mostly independent?" -> "Stay in this session?" [label="yes"];
    "Tasks mostly independent?" -> "Manual execution or brainstorm first" [label="no - tightly coupled"];
    "Stay in this session?" -> "developing-with-subagents" [label="yes"];
    "Stay in this session?" -> "executing-plans" [label="no - parallel session"];
}
```

**vs. Executing Plans (parallel session):**

- Same session (no context switch)
- Fresh subagent per task (no context pollution)
- Two-stage review after each task: spec compliance first, then code quality
- Faster iteration (no human-in-loop between tasks)

## The Process

Copy this checklist template to track overall progress:

```
Plan Execution Progress:
- [ ] Plan read and all tasks extracted
- [ ] TodoWrite created with all tasks

Per-Task Checklist (copy for each):
Task N: [description]
- [ ] Checkpoint 1 (Task Analysis) applied
- [ ] 【CP1 Assessment】 output (standalone message)
- [ ] Implementer subagent dispatched
- [ ] Questions answered (if any)
- [ ] Implementation complete
- [ ] Checkpoint 3 (Quality Gate) applied
- [ ] Spec reviewer: ✅ compliant
- [ ] Quality review: ✅ approved (Cursor if Codex/Gemini implemented; Opus if Cursor implemented)
- [ ] Task marked complete

Final Steps:
- [ ] All tasks complete
- [ ] Final code reviewer dispatched
- [ ] finishing-development-branches invoked
```

```dot
digraph process {
    rankdir=TB;

    subgraph cluster_per_task {
        label="Per Task";
        "Route to external model (Codex/Gemini/Cursor per routing)" [shape=box];
        "External model asks questions?" [shape=diamond];
        "Answer questions, provide context" [shape=box];
        "External model implements, tests, commits" [shape=box];
        "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)" [shape=box];
        "Spec reviewer subagent confirms code matches spec?" [shape=diamond];
        "External model fixes spec gaps" [shape=box];
        "Quality review (./code-quality-reviewer-prompt.md)" [shape=box];
        "Quality reviewer approves?" [shape=diamond];
        "External model fixes quality issues (max 3 loops)" [shape=box];
        "Mark task complete in TodoWrite" [shape=box];
    }

    "Read plan, extract all tasks with full text, note context, create TodoWrite" [shape=box];
    "More tasks remain?" [shape=diamond];
    "Dispatch final code reviewer subagent for entire implementation" [shape=box];
    "Use superpowers:finishing-development-branches" [shape=box style=filled fillcolor=lightgreen];

    "Read plan, extract all tasks with full text, note context, create TodoWrite" -> "Route to external model (Codex/Gemini/Cursor per routing)";
    "Route to external model (Codex/Gemini/Cursor per routing)" -> "External model asks questions?";
    "External model asks questions?" -> "Answer questions, provide context" [label="yes"];
    "Answer questions, provide context" -> "Route to external model (Codex/Gemini/Cursor per routing)";
    "External model asks questions?" -> "External model implements, tests, commits" [label="no"];
    "External model implements, tests, commits" -> "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)";
    "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)" -> "Spec reviewer subagent confirms code matches spec?";
    "Spec reviewer subagent confirms code matches spec?" -> "External model fixes spec gaps" [label="no"];
    "External model fixes spec gaps" -> "Dispatch spec reviewer subagent (./spec-reviewer-prompt.md)" [label="re-review"];
    "Spec reviewer subagent confirms code matches spec?" -> "Quality review (./code-quality-reviewer-prompt.md)" [label="yes"];
    "Quality review (./code-quality-reviewer-prompt.md)" -> "Quality reviewer approves?";
    "Quality reviewer approves?" -> "External model fixes quality issues (max 3 loops)" [label="no"];
    "External model fixes quality issues (max 3 loops)" -> "Quality review (./code-quality-reviewer-prompt.md)" [label="re-review"];
    "Quality reviewer approves?" -> "Mark task complete in TodoWrite" [label="yes"];
    "Mark task complete in TodoWrite" -> "More tasks remain?";
    "More tasks remain?" -> "Route to external model (Codex/Gemini/Cursor per routing)" [label="yes"];
    "More tasks remain?" -> "Dispatch final code reviewer subagent for entire implementation" [label="no"];
    "Dispatch final code reviewer subagent for entire implementation" -> "Use superpowers:finishing-development-branches";
}
```

## Prompt Templates

- `./implementer-prompt.md` - Dispatch implementer subagent (legacy template — prefer routing to external models via MCP)
- `./spec-reviewer-prompt.md` - Dispatch spec compliance reviewer subagent
- `./code-quality-reviewer-prompt.md` - Dispatch code quality reviewer (determines Cursor vs Opus)

## Model Strategy

Route implementation to external models. Claude orchestrates only.

| Role | Model | Selection Rule |
| ---- | ----- | -------------- |
| Backend implementation | Codex MCP (`mcp__codex__codex`) | CODEX routing |
| Frontend implementation | Gemini MCP (`mcp__gemini__gemini`) | GEMINI routing |
| General implementation | Cursor MCP (`mcp__cursor__cursor`) | CURSOR routing |
| Spec Reviewer | Opus (default) | Always Opus |
| Quality Reviewer | Cursor or Opus | `Reviewer = (Implementer == Cursor ? Opus : Cursor)` |
| Exploration | `model: haiku` | Flexible |

## Collaboration Checkpoints

Apply checkpoint logic from `coordinating-multi-model-work/checkpoints.md` at these stages:

**► Checkpoint 1 (Task Analysis):** Before dispatching implementer subagent:

- Collect: task files, description, complexity
- **Output a standalone `【CP1 Assessment】` block to the user BEFORE the first Task tool call**
- Check critical task conditions → Match: invoke expert model
- Evaluate general task signals → Positive: invoke

**► Checkpoint 2 (Mid-Review):** During subagent execution:

- Subagent asks question requiring external expertise → invoke domain expert
- Multiple implementation approaches debated → invoke cross-validation

**► Checkpoint 3 (Quality Gate):** After external model completes implementation:

- Implementation complete → invoke spec reviewer for compliance check
- Quality review runs after spec compliance passes (see `code-quality-reviewer-prompt.md`)
- Deterministic reviewer: `Reviewer = (Implementer == Cursor ? Opus : Cursor)`
- If Cursor quality reviewer unavailable: fall back to Opus
- If Opus quality reviewer unavailable (for Cursor-implemented work): BLOCKED
- Max 3 fix-review loops before escalating to user

## Example Workflow

```
You: I'm using Subagent-Driven Development to execute this plan.

[Read plan file once: docs/plans/feature-plan.md]
[Extract all 5 tasks with full text and context]
[Create TodoWrite with all tasks]

Task 1: Hook installation script

[Get Task 1 text and context (already extracted)]
[Dispatch implementation subagent with full task text + context]

Implementer: "Before I begin - should the hook be installed at user or system level?"

You: "User level (~/.config/superpowers/hooks/)"

Implementer: "Got it. Implementing now..."
[Later] Implementer:
  - Implemented install-hook command
  - Added tests, 5/5 passing
  - Self-review: Found I missed --force flag, added it
  - Committed

[Dispatch spec compliance reviewer]
Spec reviewer: ✅ Spec compliant - all requirements met, nothing extra

[Get git SHAs, call Cursor MCP for code quality review]
Cursor: APPROVE — Good test coverage, clean implementation. No issues found.

[Mark Task 1 complete]

Task 2: Recovery modes

[Get Task 2 text and context (already extracted)]
[Dispatch implementation subagent with full task text + context]

Implementer: [No questions, proceeds]
Implementer:
  - Added verify/repair modes
  - 8/8 tests passing
  - Self-review: All good
  - Committed

[Dispatch spec compliance reviewer]
Spec reviewer: ❌ Issues:
  - Missing: Progress reporting (spec says "report every 100 items")
  - Extra: Added --json flag (not requested)

[Implementer fixes issues]
Implementer: Removed --json flag, added progress reporting

[Spec reviewer reviews again]
Spec reviewer: ✅ Spec compliant now

[Call Cursor MCP for code quality review]
Cursor: Issues (Important): Magic number (100)

[Implementer fixes]
Implementer: Extracted PROGRESS_INTERVAL constant

[Re-submit to Cursor]
Cursor: APPROVE

[Mark Task 2 complete]

...

[After all tasks]
[Dispatch final code-reviewer]
Final reviewer: All requirements met, ready to merge

Done!
```

## Advantages

**vs. Manual execution:**

- Subagents follow TDD naturally
- Fresh context per task (no confusion)
- Parallel-safe (subagents don't interfere)
- Subagent can ask questions (before AND during work)

**vs. Executing Plans:**

- Same session (no handoff)
- Continuous progress (no waiting)
- Review checkpoints automatic

**Efficiency gains:**

- No file reading overhead (controller provides full text)
- Controller curates exactly what context is needed
- Subagent gets complete information upfront
- Questions surfaced before work begins (not after)

**Quality gates:**

- Self-review catches issues before handoff
- Two-stage review: spec compliance (Opus), then quality (deterministic reviewer)
- Review loops ensure fixes actually work (max 3 loops)
- Spec compliance prevents over/under-building
- Quality review: Cursor reviews Codex/Gemini work, Opus reviews Cursor work
- Quality review never skipped — always has a reviewer available

**Cost:**

- More subagent invocations (implementer + 2 reviewers per task)
- Controller does more prep work (extracting all tasks upfront)
- Review loops add iterations
- But catches issues early (cheaper than debugging later)

## Red Flags

**Never:**

- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed issues
- Dispatch multiple implementation subagents in parallel (conflicts)
- Make subagent read plan file (provide full text instead)
- Skip scene-setting context (subagent needs to understand where task fits)
- Ignore subagent questions (answer before letting them proceed)
- Accept "close enough" on spec compliance (spec reviewer found issues = not done)
- Skip review loops (reviewer found issues = implementer fixes = review again)
- Let implementer self-review replace actual review (both are needed)
- **Start code quality review before spec compliance is ✅** (wrong order)
- Move to next task while either review has open issues
- Skip quality review fallback when primary reviewer is unavailable
- Exceed 3 fix-review loops without escalating to user
- Let Claude write implementation code (Claude is orchestrator-only)

**If subagent asks questions:**

- Answer clearly and completely
- Provide additional context if needed
- Don't rush them into implementation

**If reviewer finds issues:**

- Implementer (same subagent) fixes them
- Reviewer reviews again
- Repeat until approved
- Don't skip the re-review

**If subagent fails task:**

- Dispatch fix subagent with specific instructions
- Don't try to fix manually (context pollution)

## Integration

**Required workflow skills:**

- **superpowers:writing-plans** - Creates the plan this skill executes
- **superpowers:requesting-code-review** - Code review template for reviewer subagents
- **superpowers:finishing-development-branches** - Complete development after all tasks
- **superpowers:coordinating-multi-model-work** - Multi-model routing for task execution

**Subagents should use:**

- **superpowers:practicing-test-driven-development** - Subagents follow TDD for each task

**Alternative workflow:**

- **superpowers:executing-plans** - Use for parallel session instead of same-session execution

## Multi-Model Task Dispatch

**Related skill:** superpowers-ccg:coordinating-multi-model-work

At checkpoints, apply semantic routing from `coordinating-multi-model-work/routing-decision.md`:

- **Routing decision (Claude never implements):**
  - Clear backend task (API, database, server logic) → **CODEX** (`mcp__codex__codex`)
  - Clear frontend task (UI, components, styles) → **GEMINI** (`mcp__gemini__gemini`)
  - Debugging, refactoring, DevOps, general implementation → **CURSOR** (`mcp__cursor__cursor`)
  - Full-stack integration or critical task → **CROSS_VALIDATION** (multiple MCP tools)
  - Documentation-only (no code) → **CLAUDE** (orchestration)

- **Check for Model Hint:** If task includes hint, use as guidance

- **Notify user:** "I will use [model] to implement [task name]"

- **Call MCP tool** with English prompts (see `coordinating-multi-model-work/INTEGRATION.md` for templates).

**Full checkpoint logic:** See `coordinating-multi-model-work/checkpoints.md`

**Fallback (Fail-Closed):** If external models are required but unavailable or time out, STOP and follow `coordinating-multi-model-work/GATE.md` (do not proceed with task completion output).
