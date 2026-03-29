# Project Overview
- Superpowers-CCCG is a Claude Code plugin / skills framework for multi-model orchestration across Claude, Codex, Gemini, and Cursor.
- The repository is primarily markdown skills, prompt templates, shell scripts, hook config, and small supporting utilities rather than a compiled app.
- The authoritative workflow/rules document is `superpowers-ccg.md`.
- Key runtime areas: `skills/` for skill definitions, `agents/` for reusable agent specs, `commands/` for shortcut workflows, `hooks/` for Claude Code hook registration, `.claude-plugin/` for plugin metadata, and `tests/claude-code/` for skill workflow tests.