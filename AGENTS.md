# AGENTS.md

Refract is a monorepo with two shipped parts:

- `plugin/`: host plugin for Claude Code, Antigravity, Codex, and Pi. Skills, slash commands, a SessionStart hook, and a Pi extension.
- `server/`: Python 3.12 daemon and `refract` CLI. MCP tools, job scheduling, backend drivers, and a React dashboard in `server/web/`.

[`README.md`](README.md) covers usage. [`server/README.md`](server/README.md) covers configuration and the MCP tools. [`CONTRIBUTING.md`](CONTRIBUTING.md) covers code style; read it before writing code.

## Commands

```bash
# Server: run from server/
uv sync --all-extras
uv run pytest

# Plugin contract tests: run from the repository root
plugin/tests/run.sh

# Dashboard: run from server/web/
pnpm install
pnpm run typecheck && pnpm exec biome ci . && pnpm exec vitest run && pnpm run check:bundle
pnpm run e2e

# Docs site: run from site/
bundle install
bundle exec jekyll build
```

CI runs the server tests on Linux, Windows, and macOS. Keep every change portable across all three.

## Invariants

- **Versions.** The version lives in many files, listed in `scripts/bump_version.py`. Change it only through that script. Line 1 of `README.md` is `# Refract <version>`, and `server/README.md` has a `Version <version> ·` line; keep both lines intact.
- **Changelog.** Add each user-visible change as a bullet under `## Unreleased` in `CHANGELOG.md`.
- **Dashboard bundle.** The built dashboard in `server/src/refract/dashboard_static/app` is committed. After editing `server/web/src`, run `pnpm run build` and commit the new bundle; `check:bundle` fails when it is stale.
- **Pinned docs.** `plugin/tests/test-contracts.sh` asserts exact phrases in `server/README.md`, `server/CLI_ARGUMENTS.md`, the plugin skills, and `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`. Read its assertions before editing those files.
- **Manifests.** The plugin description must match across `package.json`, `plugin/package.json`, the three `plugin/.*-plugin/plugin.json` files, and `plugin/plugin.json`, which must equal `plugin/.antigravity-plugin/plugin.json`.
- **Example config.** `server/config.v3.toml` must load and use every supported key. Adding a config key means adding it there. Values stay placeholders such as `replace-me` or `example`.
- **Credentials.** Target settings other than `env` are copied into job records. Credentials go in `env` or the CLI's own login, never in `args`.

## Server conventions

- Backend execution lives in the `coding_agent_cli` library. `server/src/refract/drivers.py` adapts it and adds the permission flags. Workers launch as argv lists with `shell=False`.
- Tests that need a worker CLI use the fake CLIs in `server/tests/`, launched through `server/tests/launchers.py` so they run on Windows.
- Tests marked `live` call real worker CLIs and models. Run them only when the user asks.

## Plugin conventions

- Host names differ. Claude Code uses `refract:<skill>` and `mcp__plugin_refract_refract__<tool>`. Pi uses `<skill>` and `mcp__refract__<tool>`.
- Shared worker templates live in `plugin/shared/` and carry a `refract-shared-version` marker that the version script updates.

## Dashboard conventions

The dashboard uses pnpm, TypeScript, Vite, Tailwind CSS v4, shadcn/ui on Base UI, Zod, TanStack Query, Vitest, Playwright, and Biome. Follow the patterns already in `server/web/src`.
