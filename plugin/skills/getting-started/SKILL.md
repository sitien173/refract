---
name: Getting Started with Skills
description: Skills wiki intro - mandatory workflows, search tool, brainstorming triggers, personal skills
when_to_use: Read this FIRST at start of each conversation when skills are active
version: 3.0.0
---

# Getting Started with Skills

Two skill libraries work together:
- **Core skills** at `${CLAUDE_PLUGIN_ROOT}/skills/` (from plugin)
- **Personal skills** at `~/.config/superpowers/skills/` (yours to create and share)

Personal skills shadow core skills when names match.

## Just Read This Guide?

**RIGHT NOW**: Run this to see what skills are available:
```bash
${CLAUDE_PLUGIN_ROOT}/skills/getting-started/list-skills
```

**THEN**: Follow the workflows below based on what your partner is asking for.

## How to Reference Skills

**DO NOT use @ links** - they force-load entire files, burning 200k+ context instantly.

**INSTEAD, use skill path references:**
- Format: `skills/category/skill-name` (no @ prefix, no /SKILL.md suffix)
- Example: `skills/collaboration/brainstorming` or `skills/testing/test-driven-development`
- Load with Read tool only when needed

**When you see skill references in documentation:**
- `skills/path/name` → Check personal first (`~/.config/superpowers/skills/path/name/SKILL.md`)
- If not found, check core (`${CLAUDE_PLUGIN_ROOT}/skills/path/name/SKILL.md`)
- Load supporting files only when implementing

## Mandatory Workflow 1: Brainstorming Before Coding

**When your human partner wants to start a project, no matter how big or small:**

**YOU MUST immediately read:** skills/collaboration/brainstorming

**Don't:**
- Jump straight to code
- Wait for /brainstorm command
- Skip brainstorming because you "understand the idea"

**Why:** Just writing code is almost never the right first step. We always understand requirements and plan first.

## Mandatory Workflow 2: Before ANY Task

**1. List available skills** (to avoid useless searches):
```bash
${CLAUDE_PLUGIN_ROOT}/skills/getting-started/list-skills
```

**2. Search skills** (when you need something specific):
```bash
${CLAUDE_PLUGIN_ROOT}/skills/getting-started/skills-search PATTERN
```

**3. Search conversations:**
Dispatch subagent (see Workflow 3) to check for relevant past work.

**If skills found:**
1. READ the skill: `${CLAUDE_PLUGIN_ROOT}/skills/path/skill-name/SKILL.md`
2. ANNOUNCE usage: "I'm using the [Skill Name] skill"
3. FOLLOW the skill (many are rigid requirements)

**"This doesn't count as a task" is rationalization.** Skills/conversations exist and you didn't search for them or didn't use them = failed task.

## Mandatory Workflow 3: Historical Context Search

**When:** Your human partner mentions past work, issue feels familiar, starting task in familiar domain, stuck/blocked, before reinventing

**When NOT:** Info in current convo, codebase state questions, first encounter, partner wants fresh thinking

**How (use subagent for 50-100x context savings):**
1. Dispatch subagent with template: `${CLAUDE_PLUGIN_ROOT}/skills/collaboration/remembering-conversations/tool/prompts/search-agent.md`
2. Receive synthesis (200-1000 words) + source pointers
3. Apply insights (never load raw .jsonl files)

**Example:**
```
Partner: "How did we handle auth errors in React Router?"
You: Searching past conversations...
[Dispatch subagent → 350-word synthesis]
[Apply without loading 50k tokens]
```

**Red flags:** Reading .jsonl files directly, pasting excerpts, asking "which conversation?", browsing archives

**Pattern:** Search → Subagent synthesizes → Apply. Fast, focused, context-efficient.

## Announcing Skill Usage

**Every time you start using a skill, announce it:**

"I'm using the [Skill Name] skill to [what you're doing]."

**Examples:**
- "I'm using the Brainstorming skill to refine your idea into a design."
- "I'm using the Test-Driven Development skill to implement this feature."
- "I'm using the Systematic Debugging skill to find the root cause."
- "I'm using the Refactoring Safely skill to extract these methods."

**Why:** Transparency helps your human partner understand your process and catch errors early.

## Skills with Checklists

**If a skill contains a checklist, you MUST create TodoWrite todos for EACH checklist item.**

**Don't:**
- Work through checklist mentally
- Skip creating todos "to save time"
- Batch multiple items into one todo
- Mark complete without doing them

**Why:** Checklists without TodoWrite tracking = steps get skipped. Every time.

**Examples:** TDD (write test, watch fail, implement, verify), Systematic Debugging (4 phases), Writing Skills (RED-GREEN-REFACTOR)

## How to Read a Skill

1. **Frontmatter** - `when_to_use` match your situation?
2. **Overview** - Core principle relevant?
3. **Quick Reference** - Scan for your pattern
4. **Implementation** - Full details
5. **Supporting files** - Load only when implementing

**Many skills contain rigid rules (TDD, debugging, verification).** Follow them exactly. Don't adapt away the discipline.

**Some skills are flexible patterns (architecture, naming).** Adapt core principles to your context.

The skill itself tells you which type it is.

## Referencing Skills in Documentation

**When writing documentation that references other skills:**

Use path format without `@` prefix or `/SKILL.md` suffix:
- ✅ Good: `skills/testing/test-driven-development`
- ✅ Good: `skills/debugging/systematic-debugging`
- ❌ Bad: `@skills/testing/test-driven-development/SKILL.md` (force-loads, burns context)

**Why no @ links:** `@` syntax force-loads files immediately, consuming 200k+ context before you need them.

**To read a skill reference:** Use Read tool on `${CLAUDE_PLUGIN_ROOT}/skills/category/skill-name/SKILL.md`

## Instructions ≠ Permission to Skip Workflows

Your human partner's specific instructions describe WHAT to do, not HOW.

"Add X", "Fix Y" = the goal, NOT permission to skip brainstorming, TDD, or RED-GREEN-REFACTOR.

**Red flags:** "Instruction was specific" • "Seems simple" • "Workflow is overkill"

## Writing and Sharing Skills

**All personal skills are written to `~/.config/superpowers/skills/`**

**Before writing ANY skill:**

1. **STOP** - Even if your human partner gave specific instructions
2. **Read skills/meta/writing-skills**
3. **Follow the TDD process** - No skill without failing test first

**Your human partner's specific instruction is NOT implicit permission to skip the process.**

**Red flags:**
- "Just a small addition"
- "Instruction was specific, so I can proceed"

**All of these mean: STOP and follow writing-skills process.**

**Want to share a skill with everyone?**
- See skills/meta/sharing-skills for how to contribute to core superpowers

**Want a skill that doesn't exist?**
- Write it yourself (see skills/meta/writing-skills) and share it!
- Or open an issue at https://github.com/obra/superpowers/issues

## Summary

**Starting conversation?** You just read this. Good.

**Starting any task?** Run skills-search first, announce usage, follow what you find.

**Skill has checklist?** TodoWrite for every item.

**Skills are mandatory when they exist, not optional.**


## Last thing

In the first response after reading this guide, you MUST announce to the user that you have read the getting started guide
