---
layout: default
title: Getting started
nav_order: 2
---

# Getting started

## 1. Install the server

```bash
uv tool install "refract @ git+https://github.com/sitien173/refract#subdirectory=server"
```

## 2. Configure targets and profiles

Create `~/.refract/config.toml`. Start from [`server/config.v3.toml`](https://github.com/sitien173/refract/blob/main/server/config.v3.toml), which shows every supported key:

```toml
[daemon]
default_profile = "base"

[[targets]]
id = "codex-code"
backend = "codex"
reasoning = "high"

[[targets]]
id = "claude-review"
backend = "claude"
model = "sonnet"
isolated = true
read_only = true

[profiles.base]
implement = "codex-code"
review = "claude-review"
consult = ["claude-review", "codex-code"]
```

> In Claude Code, run `/refract:setting-up-refract` after installing the plugin. It scans your worker CLIs and writes this file with you.

## 3. Check and start the daemon

```bash
refract doctor
refract serve
```

`refract doctor` exits 0 when the state directory is writable and every target executable resolves. The daemon listens on `http://127.0.0.1:8765/mcp`.

## 4. Install the plugin

Run `refract install` with the host you use:

```bash
refract install -p claude
refract install -p claude,codex,pi
refract install -p all
```

`-p` takes `claude`, `codex`, `agy`, `agy-ide`, `pi`, or `all`. Pass a comma list or repeat the flag. `all` means every host CLI found on PATH, plus `agy-ide` when the Antigravity IDE is present. Add `--dry-run` to print the planned commands without running them. Use `refract uninstall -p <host>` to remove the plugin. See the Installing section of [`plugin/README.md`](https://github.com/sitien173/refract/blob/main/plugin/README.md) for scopes and sources.

The standalone Antigravity IDE has no plugin CLI, so `agy-ide` works differently: Refract copies the plugin files itself, to `~/.gemini/config/plugins/refract/` for `user` scope or `.agents/plugins/refract/` in the current directory for `project` scope. Pass a local clone with `--source`. Refract leaves a marker in what it copies and will not delete a directory it did not install.

To install by hand, use the host's own commands.

Claude Code:

```bash
claude plugin marketplace add sitien173/refract
claude plugin install refract@refract
```

Codex:

```bash
codex plugin marketplace add sitien173/refract
codex plugin add refract@refract
```

Antigravity:

```bash
agy plugin install https://github.com/sitien173/refract
```

Pi:

```bash
pi install https://github.com/sitien173/refract
```

When the daemon is not running, the plugin's SessionStart hook starts `refract serve` in the background.

## 5. Run the workflow

| Command | Purpose |
| --- | --- |
| `/refract:brainstorm <idea>` | Clarify intent and trade-offs, then write a design. |
| `/refract:write-plan <design>` | Turn a confirmed design into a phase plan. |
| `/refract:execute-plan [target]` | Run one wave of phases through all three gates. |
| `/refract:execute-plan-all [target]` | Run every wave through final audit without pausing. |

In Pi, drop the `refract:` prefix, for example `/brainstorm`.

Source: [README.md](https://github.com/sitien173/refract/blob/main/README.md)
