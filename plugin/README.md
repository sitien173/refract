# superpowers-ccg

A Claude Code plugin that runs coding work through three gates:
**Plan → Execute → Review**. Claude acts as Coordinator: it brainstorms and
plans with you, delegates implementation and independent review to external
workers through OpenMCP, and owns every Git commit, anchor, and verification.

## Prerequisite: OpenMCP

Execute and Review require a running OpenMCP server. The bundled MCP entry
(`.mcp.json`) connects to `http://127.0.0.1:8765/mcp` by default. To use a
different host or port, export `OPENMCP_URL` before starting Claude Code:

```bash
export OPENMCP_URL=http://127.0.0.1:9000/mcp
```

Without OpenMCP, brainstorming and plan authoring still work; consultation is
skipped and recorded, and execution stops at the setup check.

## Install

```text
/plugin marketplace add sitien173/superpowers-ccg
/plugin install superpowers-ccg@superpowers-ccg-marketplace
```

## Commands

| Command | Purpose |
| --- | --- |
| `/superpowers-ccg:brainstorm <idea>` | Clarify intent and trade-offs; write `DESIGN.md`. |
| `/superpowers-ccg:write-plan <design>` | Turn a confirmed design into a phase plan. |
| `/superpowers-ccg:execute-plan [target]` | Run or resume one phase through all three gates. |

## Skills

- `using-superpowers` — entry point; decides when coordination applies.
- `coordinating-multi-model-work` — OpenMCP lifecycle, Git ownership, review, handover.
- `brainstorming`, `writing-plans`, `executing-plans` — the three gates.
- `systematic-debugging`, `test-driven-development`, `verifying-before-completion` — process discipline.
- `using-git-worktrees` — optional isolated workspace before registration.

## Layout

```text
commands/   slash commands
skills/     SKILL.md files and references
shared/     worker contract, response protocol, phase templates
hooks/      SessionStart hook that loads the coordinator context
tests/      contract tests (`tests/run.sh`)
docs/plans/ worked examples of the folder-plan layout, produced by this plugin
```

## Development

```bash
tests/run.sh
```

Runs the hook and contract tests, then `claude plugin validate` when the CLI is
available. Bump `version` in `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, and the
`ccg-shared-version` marker in every `shared/*.md` together; the tests assert
they match.

## License

MIT
