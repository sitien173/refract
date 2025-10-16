# Claude Commands

Slash commands for Claude that reference skills.

## Available Commands

- `/brainstorm` - Interactive idea refinement using Socratic method (→ `@skills/collaboration/brainstorming/SKILL.md`)
- `/write-plan` - Create detailed implementation plan (→ `@skills/collaboration/writing-plans/SKILL.md`)
- `/execute-plan` - Execute plan in batches with review (→ `@skills/collaboration/executing-plans/SKILL.md`)

## Format

Each command is a simple markdown file containing a single `@` reference to a skill:

```markdown
@skills/collaboration/brainstorming/SKILL.md
```

When you run the command (e.g., `/brainstorm`), Claude loads and follows that skill.

## Creating Custom Commands

To add your own commands:

1. Create `your-command.md` in this directory
2. Add a single line referencing a skill:
   ```markdown
   @skills/your-category/your-skill/SKILL.md
   ```
3. The command `/your-command` is now available

## Installation

These commands are automatically symlinked to `~/.claude/commands/` by the clank installer.

See `@skills/meta/installing-skills/SKILL.md` for installation details.
