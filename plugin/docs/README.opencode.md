# Superpowers-CCG for OpenCode

This repository can also be used from OpenCode through a lightweight plugin entrypoint at `.opencode/plugin/superpowers.js`.

## Install

```bash
mkdir -p ~/.config/opencode
cd ~/.config/opencode
npm install @opencode-ai/plugin

git clone https://github.com/sitien173/superpowers-ccg.git ~/.config/opencode/superpowers-ccg

mkdir -p ~/.config/opencode/plugins
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/plugin/superpowers.js ~/.config/opencode/plugins/superpowers-ccg.js

mkdir -p ~/.config/opencode/commands
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/brainstorm.md ~/.config/opencode/commands/brainstorm.md
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/write-plan.md ~/.config/opencode/commands/write-plan.md
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/execute-plan.md ~/.config/opencode/commands/execute-plan.md
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/debug.md ~/.config/opencode/commands/debug.md
```

Restart OpenCode after the symlinks are in place.

## What It Loads

- The repo workflow guide from `superpowers-ccg.md`
- All bundled skills from `skills/`
- Personal skills from `~/.config/opencode/skills/`
- Project-local skills from `.opencode/skills/`
- Global slash commands linked from `.opencode/commands/` into `~/.config/opencode/commands/`

Priority order is `project:` > personal > `superpowers:`.

## Tool Mapping

- `TodoWrite` -> `update_plan`
- Claude `Task` subagents -> OpenCode @mentions
- `Skill` tool -> `use_skill`

## Usage

Ask OpenCode to call:

```text
find_skills
```

or:

```text
use_skill with skill_name: "superpowers:brainstorming"
```

You should also see native OpenCode slash commands from this repo:

- `/brainstorm`
- `/write-plan`
- `/execute-plan`
- `/debug`

OpenCode loads custom commands from `.opencode/commands/`, so these are the visible entrypoints for the main Superpowers workflows.

If you only install the plugin symlink and skip the command symlinks, the tools will still exist, but the slash commands will not appear in the TUI.

## Testing

The repo includes a static OpenCode suite that does not require OpenCode itself:

```bash
./tests/opencode/run-tests.sh
```

Integration coverage is available when `opencode` is installed:

```bash
./tests/opencode/run-tests.sh --integration
```
