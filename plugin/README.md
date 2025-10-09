# Superpowers

Give Claude Code superpowers with a comprehensive skills library of proven techniques, patterns, and tools.

## What You Get

- **Testing Skills** - TDD, async testing, anti-patterns
- **Debugging Skills** - Systematic debugging, root cause tracing, verification
- **Collaboration Skills** - Brainstorming, planning, code review, parallel agents
- **Meta Skills** - Creating, testing, and contributing skills

Plus:
- **Slash Commands** - `/brainstorm`, `/write-plan`, `/execute-plan`
- **Skills Search** - Grep-powered discovery of relevant skills
- **Gap Tracking** - Failed searches logged for skill creation

## Installation

### Via Plugin Marketplace (Recommended)

```bash
# In Claude Code
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

That's it! The plugin will:
- Inject skills library into your session context
- Make skills searchable via `${CLAUDE_PLUGIN_ROOT}/skills/getting-started/skills-search`
- Add `/brainstorm`, `/write-plan`, and `/execute-plan` commands
- Create `~/.superpowers/` for local data

### Verify Installation

```bash
# Check that commands appear
/help

# Should see:
# /brainstorm - Interactive design refinement
# /write-plan - Create implementation plan
# /execute-plan - Execute plan in batches
```

## Quick Start

### Finding Skills

Search for relevant skills before starting any task:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/getting-started/skills-search 'test.*driven|TDD'
${CLAUDE_PLUGIN_ROOT}/skills/getting-started/skills-search 'debug.*systematic'
${CLAUDE_PLUGIN_ROOT}/skills/getting-started/skills-search 'refactor'
```

### Using Slash Commands

**Brainstorm a design:**
```
/brainstorm
```

**Create an implementation plan:**
```
/write-plan
```

**Execute the plan:**
```
/execute-plan
```

## What's Inside

### Skills Library

**Testing** (`skills/testing/`)
- test-driven-development - RED-GREEN-REFACTOR cycle
- condition-based-waiting - Async test patterns
- testing-anti-patterns - Common pitfalls to avoid

**Debugging** (`skills/debugging/`)
- systematic-debugging - 4-phase root cause process
- root-cause-tracing - Find the real problem
- verification-before-completion - Ensure it's actually fixed
- defense-in-depth - Multiple validation layers

**Collaboration** (`skills/collaboration/`)
- brainstorming - Socratic design refinement
- writing-plans - Detailed implementation plans
- executing-plans - Batch execution with checkpoints
- dispatching-parallel-agents - Concurrent subagent workflows
- remembering-conversations - Search past work
- using-git-worktrees - Parallel development branches
- requesting-code-review - Pre-review checklist
- receiving-code-review - Responding to feedback

**Meta** (`skills/meta/`)
- creating-skills - Document new techniques
- testing-skills-with-subagents - Validate skill quality
- gardening-skills-wiki - Maintain and improve skills

### Commands

- **brainstorm.md** - Interactive design refinement using Socratic method
- **write-plan.md** - Create detailed implementation plans
- **execute-plan.md** - Execute plans in batches with review checkpoints

### Tools

- **skills-search** - Grep-powered skill discovery
- **search-conversations** - Semantic search of past Claude sessions

## How It Works

1. **SessionStart Hook** - Injects skills library context at session start
2. **Skills Discovery** - `skills-search` finds relevant skills using grep patterns
3. **Mandatory Workflow** - Skills become required when they exist for your task
4. **Gap Tracking** - Failed searches logged to `~/.superpowers/search-log.jsonl`

## Philosophy

- **Test-Driven Development** - Write tests first, always
- **Systematic over ad-hoc** - Process over guessing
- **Complexity reduction** - Simplicity as primary goal
- **Evidence over claims** - Verify before declaring success
- **Domain over implementation** - Work at problem level, not solution level

## Data Directory

The plugin creates `~/.superpowers/` for local data:

```
~/.superpowers/
├── search-log.jsonl          # Failed skill searches
└── conversation-index/       # Indexed past conversations (if enabled)
```

## Contributing

Want to add a skill? See `skills/meta/creating-skills/SKILL.md`

Missing a skill? Edit `skills/REQUESTS.md` or open an issue

## License

MIT License - see LICENSE file for details

## Support

- **Issues**: https://github.com/obra/superpowers/issues
- **Marketplace**: https://github.com/obra/superpowers-marketplace
