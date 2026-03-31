# Style and Conventions

## Skill File Structure
Each skill lives in `skills/<skill-name>/SKILL.md` with YAML frontmatter:
```markdown
---
name: skill-name
description: "one-line description for skill discovery"
---

[skill content / instructions]
```

Supporting files (e.g., `GATE.md`, `routing-decision.md`, `checkpoints.md`) live in the same subdirectory.

## Skill Authoring Rules (Iron Laws)
- **TDD required**: Write a failing test BEFORE implementing any skill
- Skills are in the `superpowers-ccg:` namespace
- Use `superpowers-ccg:writing-skills` skill when creating/editing skills

## Naming
- Skill directories: `kebab-case`
- Skill names in frontmatter: `kebab-case`
- Skill invocation: `superpowers-ccg:<skill-name>`

## Markdown Style
- Use `##` for top-level sections within skills
- Tables for reference material (routing rules, skill lists)
- Code blocks with language identifiers
- Keep skill instructions action-oriented and imperative

## Commit Messages
- Format: `type: description` (e.g., `feat: add skill`, `fix: correct routing`)
- Types: `feat`, `fix`, `docs`, `refactor`, `test`

## Code (lib/skills-core.js)
- Node.js, no transpilation
- Minimal dependencies

## Hooks
- Bash scripts in `hooks/` directory
- Registered in `hooks/hooks.json`
- Windows-compatible via `run-hook.cmd` wrapper
