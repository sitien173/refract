# Superpowers-CCG for OpenCode

This repository can also be used from OpenCode through a lightweight plugin entrypoint at `.opencode/plugin/superpowers.js`.

## Install

```bash
mkdir -p ~/.config/opencode/superpowers
git clone https://github.com/sitien173/superpowers-ccg.git ~/.config/opencode/superpowers

mkdir -p ~/.config/opencode/plugin
ln -sf ~/.config/opencode/superpowers/.opencode/plugin/superpowers.js ~/.config/opencode/plugin/superpowers.js
```

Restart OpenCode after the symlink is in place.

## What It Loads

- The repo workflow guide from `superpowers-ccg.md`
- All bundled skills from `skills/`
- Personal skills from `~/.config/opencode/skills/`
- Project-local skills from `.opencode/skills/`

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

## Testing

The repo includes a static OpenCode suite that does not require OpenCode itself:

```bash
./tests/opencode/run-tests.sh
```

Integration coverage is available when `opencode` is installed:

```bash
./tests/opencode/run-tests.sh --integration
```
