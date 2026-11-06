# Refract 2.5.0

Refract combines a Claude Code, Codex, Pi, and Antigravity CLI plugin with a local MCP orchestration server. The plugin coordinates planning, implementation, and review. The server runs durable jobs through installed coding-agent CLIs.

## Repository layout

- `plugin/` contains manifests, commands, skills, hooks, shared contracts, and tests.
- `server/` contains the Python MCP server.
- `docs/diagrams/` contains editable diagrams and exported images.

## Install

After the Refract marketplace is published, add it and install the plugin:

```bash
claude plugin marketplace add sitien173/refract
claude plugin install refract@refract
```

Install the server from the repository:

```bash
cd server
uv sync --all-extras
```

Before starting it, create `~/.refract/config.toml` with the installed targets, profiles, and `default_profile`. See [server configuration](server/README.md#configuration). The server reads `~/.refract/config.toml` by default. Set `REFRACT_HOME` to select another state directory. The MCP endpoint defaults to `http://127.0.0.1:8765/mcp`.

Start the server with:

```bash
cd server
uv run refract serve
```

## Dashboard

The loopback-only dashboard is a React single-page console backed by the `/dashboard/api` JSON API. Open `http://127.0.0.1:8765/dashboard` for the live job console, `/dashboard/jobs/{job_id}` for a deep-linked job, or `/dashboard/targets` for target and configuration health. The selected job and list filters are kept in the URL. Job and transcript data poll while relevant, and the console supports cancelling, retrying, and answering pending questions with CSRF-guarded actions.

To rebuild the committed frontend bundle:

```bash
cd server/web
npm ci
npm run build
npm run check:bundle
```

## Manual state migration

These steps document a manual migration from the prior product state. They have not been run by this plan.

Renaming files does not carry job history into v3. This server uses schema 18 and does not migrate older databases. On startup, a database with any other older schema is renamed to `refract.db.v2.bak`, together with its `-wal` and `-shm` sidecars, and a fresh schema 18 database is created. No data is deleted. If a `.v2.bak` file already exists, startup stops and the database is not modified; move the old backup away first. A database with a schema newer than 18 is refused and left unchanged. To return to the prior version, stop the daemon and restore the `.v2.bak` files under their original names. Select another state directory with `REFRACT_HOME` to start fresh without touching the old one.

1. Stop the daemon. Back up the complete state directory, including SQLite sidecars.
2. Move the state directory, then rename files matching `openmcp.db*` to `refract.db*` and `openmcp.log*` to `refract.log*` inside `~/.refract`. Preserve each file's suffix, including SQLite sidecars.

   ```bash
   mv ~/.openmcp ~/.refract
   ```

3. Move each project's `.openmcp/` directory to `.refract/`.
4. In each repository, copy the old Git tracking value to the new key:

   ```bash
   git config --local refract.plans.tracking "$(git config --local ccg.plans.tracking)"
   ```

5. Rename `OPENMCP_*` environment variables to `REFRACT_*`.
6. In Claude settings, replace the `superpowers-ccg` marketplace and plugin with `refract`. Update permission entries containing `mcp__plugin_superpowers-ccg_openmcp__*` or `.openmcp`.

## Migrating config to v3

The v3 server loads one flat snake_case config. A removed key fails the load with `<key> has been removed` and, where one exists, the replacement. Rewrite each removed key as listed:

| Removed key | Replacement |
|---|---|
| `[langfuse]` | removed, no replacement |
| `[daemon].history_turns` | removed, no replacement |
| `[daemon].history_bytes` | removed, no replacement |
| `[retryPolicies]` | use targets[].retry |
| `targets[].retryPolicy` | use targets[].retry |
| `[envs]` | use targets[].env |
| `targets[].envs_vars` | use targets[].env |
| `targets[].envs` | use targets[].env |
| `targets[].contextWindow` | use targets[].context_window |
| `targets[].profile` | use targets[].backend_profile |
| `profiles workflow max_attempts` | use targets[].retry.attempts |
| `${NAME} in targets[].env` | write the literal value |
| `[project]` | pass profile on submit |
| `[logging].format` | removed, no replacement |
| `[logging].console` | removed, no replacement |
| `[logging].capture_warnings` | removed, no replacement |

- A named retry policy becomes an inline table on each target that used it: `retry = { attempts = 2, codes = ["rate_limit"], patterns = ["temporarily unavailable"] }`. The old `retryAttempt`, `errorCodes` and `errorPatterns` become `attempts`, `codes` and `patterns`.
- Shared env sets are gone. Copy the values each target selected into its own `env` table. Write template values out literally; the daemon environment is already inherited.
- A project `.refract/config.toml` may hold only `[profiles.<name>]` entries and `[[targets]]` entries with `id` and `env`. Pass the project profile on `submit` instead of setting a project default.
- Logs are text only. The `REFRACT_LOG_FORMAT`, `REFRACT_LOG_CONSOLE` and `REFRACT_LOG_CAPTURE_WARNINGS` variables and the `--log-format` and `--log-console` flags are gone.
- Unknown keys also fail the load, so a typo is reported instead of ignored.

[`server/config.v3.toml`](server/config.v3.toml) is a complete v3 example.

## Lineage

Refract 1.0.0 combines superpowers-ccg 12.0.0 and openmcp 2.0.0.
