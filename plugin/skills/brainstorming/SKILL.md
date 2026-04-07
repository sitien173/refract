---
name: brainstorming
description: "Explores user intent, requirements and design through collaborative dialogue before implementation. Use when: creating features, building components, adding functionality, modifying behavior, or starting any creative work. Keywords: design, requirements, spec, ideation, planning"
---

# Brainstorming Ideas Into Designs

## Overview

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design in small sections (200-300 words), checking after each section whether it looks right so far.

## Protocol Threshold (Required)

Follow `skills/shared/protocol-threshold.md`. The hook injects CP reminders automatically.

## The Process

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

**Model tip for exploration:** When dispatching subagents to explore the codebase, use `model: haiku` for fast, cost-effective searches. Haiku excels at file pattern matching and quick lookups.

**Supplementary tools (optional, enhance research):**
- **Grok Search (Tavily):** If the idea involves unfamiliar tech, current trends, or competitive analysis — use `mcp__grok-search__web_search` to gather real-time information before proposing approaches. Especially useful when the user references a library, service, or pattern you're uncertain about.
- **Auggie:** If the project is large (>10 files involved) — use Auggie for full-context semantic codebase retrieval to understand the existing architecture and likely implementation anchors.
- See `skills/shared/supplementary-tools.md` for full reference.

**► CP1 (Task Assessment & Routing):** After understanding the idea, apply `coordinating-multi-model-work/checkpoints.md`.

**Exploring approaches:**

- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**CP2 note:** CP2 is the external execution phase and starts only after the design is routed into implementation.

**Presenting the design:**

- Once you believe you understand what you're building, present the design
- Break it into sections of 200-300 words
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

## After the Design

**Documentation (must not be skipped):**

Once the user confirms the design looks right, do ALL of the following:

1. Ensure the output directory exists (create `docs/plans/` if missing)
2. Write the final design content to `docs/plans/YYYY-MM-DD-<topic>-design.md`
3. Then tell the user the file path you wrote

Only commit if the user explicitly asks you to commit.

**Implementation (if continuing):**

- Ask: "Ready to turn this into an implementation plan?"
- Use superpowers:writing-plans to create detailed implementation plan

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design in sections, validate each
- **Be flexible** - Go back and clarify when something doesn't make sense

## Multi-Model Design Validation

See `skills/shared/multi-model-integration-section.md` for routing, invocation, and fallback rules.
