# Refract

A Claude Code plugin that runs coding work through three gates:
**Plan → Execute → Review**. Claude acts as Coordinator: it brainstorms and
plans with you, delegates implementation and independent review to external
workers through Refract, and owns every Git commit, anchor, and verification.

## Prerequisite: Refract

Execute and Review require a running Refract server. The `.mcp.json` entry
uses the default endpoint documented in the
[tool contract](skills/coordinating-multi-model-work/references/tool-contract.md).
For another host or port, export `REFRACT_URL` before starting Claude Code:

```bash
export REFRACT_URL=http://127.0.0.1:9000/mcp
```

At session start the plugin runs `refract status` and starts a detached
`refract serve` when the daemon is not running and `refract` is on PATH.

Without Refract, brainstorming and plan authoring still work; consultation is
skipped and recorded, and execution stops at the setup check.

## Install

After the marketplace is published, install the plugin with:

```bash
claude plugin marketplace add sitien173/refract
claude plugin install refract@refract
```

For Antigravity CLI (`agy`):

```bash
agy plugin install https://github.com/sitien173/refract
```

For the Pi coding agent (`pi`), install from GitHub or from a local clone:

```bash
pi install https://github.com/sitien173/refract
pi install /path/to/refract/plugin
```

Pi reads the `pi` manifest in `package.json`: the repository-root manifest
for a GitHub install, `plugin/package.json` for a local `plugin/` path. The
`pi/extensions/refract.ts` extension registers the Refract MCP server at
`REFRACT_URL` and adds the coordinator context. Pi names skills and tools
without the Claude plugin namespace: `/skill:using-refract`. The skills and
hook name MCP tools by the `refract` server, not by a host-specific prefix.

### Run without Refract

Set `REFRACT_DISABLE=1` for any host; `true` and `yes` also work. The
SessionStart hook then skips the daemon check and replaces the coordinator
context with a notice to ignore Refract skills, commands, and MCP tools unless
the user asks for them. The skills and MCP server stay installed, so this
relies on the agent following the notice:

```bash
REFRACT_DISABLE=1 claude -p "Summarize this repository"
REFRACT_DISABLE=1 codex exec "Summarize this repository"
REFRACT_DISABLE=1 agy -p "Summarize this repository"
```

To unload the plugin itself for one Claude Code run, override
`enabledPlugins` with the plugin ID from `/plugin`:

```bash
claude -p --settings '{"enabledPlugins":{"refract@refract":false}}' "Summarize this repository"
```

Codex reads `plugins."<plugin>@<marketplace>".enabled` from `config.toml`, and
`-c` overrides it for one run. Take the ID from `codex plugin list`:

```bash
codex exec -c 'plugins."refract@<marketplace>".enabled=false' "Summarize this repository"
```

Antigravity disables plugins only persistently, with `agy plugin disable refract`.

### Run Pi without Refract

The extension adds a `--no-refract` flag. It skips the daemon check and the
MCP server for one run and injects the same ignore notice. The Refract skills
and commands still load:

```bash
pi -p --no-refract "Summarize this repository"
```

`REFRACT_DISABLE=1` does the same; it also accepts `true` and `yes`:

```bash
REFRACT_DISABLE=1 pi -p "Summarize this repository"
```

Pi has no flag that disables one package. To disable every extension, skill,
and prompt template for one non-interactive run:

```bash
pi -p --no-extensions --no-skills --no-prompt-templates "Summarize this repository"
```

`--no-extensions` also disables built-in MCP support; add `-e builtin:mcp` to
keep it. `--no-extensions` alone stops the coordinator context and the daemon
check but keeps the Refract skills and commands, without the ignore notice.

To disable only Refract, replace its entry in `packages` in
`~/.pi/agent/settings.json` with an empty filter. Use the `source` string Pi
recorded at install. This applies to every Pi session, interactive included:

```json
{
  "source": "../../projects/refract/plugin",
  "extensions": [],
  "skills": [],
  "prompts": []
}
```

For one run only, point `PI_CODING_AGENT_DIR` at a copy of `~/.pi/agent` with
this filter. The copy needs `auth.json` for provider credentials.

Refract Pi workers with `isolated = true` already run with
`--no-extensions --no-skills --no-prompt-templates`. A non-isolated Pi target
loads installed packages, so its workers receive the coordinator context.

## Installing

`refract install -p <host>` installs the plugin by running each host's own CLI. `refract uninstall -p <host>` removes it. `-p` takes `claude`, `codex`, `agy`, `agy-ide`, `pi`, or `all`. Pass a comma list or repeat the flag. `all` means every host CLI found on PATH, plus `agy-ide` when the Antigravity IDE is present (see Antigravity IDE below). The resolved host list always prints first as `hosts: ...`.

```bash
refract install -p claude
refract install -p claude,codex -p pi
refract install -p all --dry-run
refract uninstall -p codex
```

Claude and Codex add the `refract` marketplace, then install `refract@refract`. Antigravity runs `agy plugin install <source>`. Pi runs `pi install <source>`. The Antigravity IDE (`agy-ide`) is the one exception: Refract copies files itself.

Each host prints one result line: `installed`, `already installed`, `removed`, `not installed`, `skipped (dry run)`, or `failed: <reason>`. A failure on one host does not stop the others. A failed step prints the commands already applied and an undo command where one exists. Nothing is rolled back automatically.

### Scopes

| Host | `--scope` values |
| --- | --- |
| `claude` | `user`, `project`, `local` |
| `pi` | `user`, `project`; `project` runs `pi install -l` |
| `codex` | `user` |
| `agy` | `user` |
| `agy-ide` | `user`, `project`; `local` exits 2 |

The default is `user`. An unsupported scope exits 2 before any host command runs. A scope other than `user` acts on the current directory, which the command prints.

### Dry run

`--dry-run` prints each planned host command as `<host>: would run: <command>`. It runs no command that changes state. For `agy-ide` it prints each planned file operation instead, as `agy-ide: would copy <src> -> <dst>`, `agy-ide: would clone <url> and copy its plugin -> <dst>`, or `agy-ide: would remove <dst>`, then `agy-ide: skipped (dry run)`, and writes nothing. It still runs the read-only checks: `plugin list --json` and `plugin marketplace list --json` for Claude and Codex, `plugin list --json` for Antigravity, and a read of Pi's `settings.json`.

### Antigravity IDE

The standalone Antigravity IDE has no plugin CLI. For `agy-ide` alone, Refract writes into your home directory (or the current directory for `project`) by copying the plugin tree itself, instead of running a host CLI.

```bash
refract install -p agy-ide
refract install -p agy-ide --source /path/to/refract
refract install -p agy-ide --scope project --source /path/to/refract/plugin
refract uninstall -p agy-ide
```

- `user` scope copies to `~/.gemini/config/plugins/refract/`. `project` scope copies to `<cwd>/.agents/plugins/refract/`. `--scope local` exits 2.
- `--source` is optional. A local path must point to the repository root or to `plugin/`. Without `--source`, or with a URL, Refract runs `git clone --depth 1` into a temporary directory, copies the plugin from it, and deletes the clone. This needs `git` on PATH and network access. When the plugin is already installed, Refract does not clone.
- Refract detects the IDE by a filesystem check for `~/.gemini/antigravity-ide` or `~/.gemini/config`, not by PATH. A named `agy-ide` without either prints `agy-ide: failed: Antigravity IDE not found`.
- `-p all` includes `agy-ide` only when that check passes.
- Install writes an ownership marker, `.refract-agy-ide-install.json`, into the copied directory. Uninstall removes the directory only when that marker is present and names the same path. Refract refuses to delete a directory that is not a Refract plugin, an unmarked directory, a marker for another path, or a link, and it prints the reason.
- The `agy` CLI stages its own installs at the same `user` path. Refract does not delete that directory.
- Installing over an existing Refract install prints `already installed`. Replacing is not supported; uninstall first.

If you have the `agy` CLI, `agy plugin install https://github.com/sitien173/refract` is an alternative that installs through that CLI instead of Refract.

Antigravity does not load plugin slash commands, so the four commands are unavailable here. See Commands below for the skill names to invoke instead.

### Marketplace removal

`refract install` skips the marketplace step when a `refract` marketplace already points at the same source. A `refract` marketplace with a different source is a failure, and Refract does not overwrite it.

`refract uninstall` removes the plugin first. It removes the `refract` marketplace only when its source is Refract and no other plugin from that marketplace is still installed. When it keeps an existing `refract` marketplace, it prints `<host>: note: marketplace refract kept: <reason>`. When the plugin is not installed, uninstall leaves the marketplace alone. Pi removal uses the source string Pi stored at install time.

### Source

`--source` defaults to `https://github.com/sitien173/refract`. Claude and Codex receive it as `sitien173/refract`. A value that contains `://` or starts with `git@` is used as given. Any other value is a local path, expanded and made absolute.

`--source owner/repo` is therefore a local path, not a GitHub repository. To install a fork, pass the full URL.

A fork URL installs, but `refract update` reports a Claude Code or Pi fork as untrusted and does not update it. Codex and Antigravity installs are always updated by hand.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every host succeeded or was already in the requested state. |
| `1` | A host failed, a named host is not on PATH or, for `agy-ide`, not found, `-p all` found no host, another `refract update` or install holds the lock, or the lock file cannot be opened. |
| `2` | Usage error or unsupported scope. |

## Updating

`refract update --check` looks for newer versions of the server, the Claude Code plugin, and the Pi package, and writes the result to `${REFRACT_HOME:-~/.refract}/update-check.json`. It checks at most once per 24 hours; `refract update --check --force` ignores that limit.

`refract update` applies every available update. It refuses while the daemon has work: `Refused: <r> running, <q> queued job(s). Nothing was changed.` Run it again once the jobs finish. Otherwise it stops and restarts the daemon itself.

After applying updates it prints `Restart open Claude Code, Pi, Codex, and agy sessions to load the update.`

Codex and agy are not updated automatically. `refract update` prints the commands to run:

```bash
codex plugin marketplace upgrade && codex plugin add refract@<marketplace>
agy plugin install https://github.com/sitien173/refract
```

The SessionStart hook reads the cached check result and tells you and the model when an update is available. It makes no network call. When the cache is missing or older than 24 hours, it starts a detached `refract update --check` in the background. Set `REFRACT_NO_UPDATE_CHECK=1` to turn off the notice and the background check.

## Commands

| Command | Purpose |
| --- | --- |
| `/refract:brainstorm <idea>` | Clarify intent and trade-offs; write `DESIGN.md`. |
| `/refract:write-plan <design>` | Turn a confirmed design into a phase plan. |
| `/refract:execute-plan [target]` | Run or resume one wave of phases through all three gates. |
| `/refract:execute-plan-all [target]` | Autonomously execute all waves through final audit and consolidation. |

Antigravity (`agy` and `agy-ide`) does not load plugin slash commands, so
`/refract:brainstorm` and the other three are unavailable. Invoke the skill by
name instead:

| Command | Skill to invoke in Antigravity |
| --- | --- |
| `/refract:brainstorm` | `brainstorming` |
| `/refract:write-plan` | `writing-plans` |
| `/refract:execute-plan` | `executing-plans` |
| `/refract:execute-plan-all` | `executing-plans-autonomously` |

In Pi, drop the `refract:` prefix: `/brainstorm`, `/write-plan`,
`/execute-plan`, `/execute-plan-all`.

## Parallel phases

- A phase may declare `**Depends on:** Phase 1, Phase 3` or `**Depends on:** none`. Without the line, it depends on the previous phase.
- A wave is every phase whose dependencies have landed. A single-phase wave runs exactly as a sequential phase.
- A multi-phase wave implements each phase in its own worktree, then integrates and reviews each phase on the main checkout in plan order.
- The Coordinator waits round-robin while several jobs are active. With more than four active jobs, a worker question can expire before it is answered.
- Wave mechanics live in `skills/coordinating-multi-model-work/references/waves.md`.

## Skills

- `using-refract`: entry point; decides when coordination applies.
- `coordinating-multi-model-work`: Refract lifecycle, Git ownership, review, handover.
- `brainstorming`, `writing-plans`, `executing-plans`, `executing-plans-autonomously`: the three gates and full-plan autonomous execution.
- `systematic-debugging`, `test-driven-development`, `verifying-before-completion`: process discipline.
- `using-git-worktrees`: optional isolated workspace before registration.

## Layout

```text
commands/   slash commands
skills/     SKILL.md files and references
shared/     worker contract, response protocol, phase templates
hooks/      SessionStart hook that loads the coordinator context
pi/         Pi extension: MCP registration and coordinator context
tests/      contract tests (`tests/run.sh`)
```

## Development

```bash
tests/run.sh
```

Runs the hook and contract tests, then `claude plugin validate` and
`agy plugin validate` when the CLIs are available. Versions are bumped by
`scripts/bump_version.py`, which updates every file that holds one; the tests
assert they match.

## License

MIT
