# Refract 2.0.0

Refract combines a Claude Code, Codex, Pi, and Antigravity CLI plugin with a local MCP orchestration server and dashboard. The plugin coordinates planning, implementation, and review. The server runs durable jobs through installed coding-agent CLIs.

## Repository layout

- `plugin/` contains manifests, commands, skills, hooks, shared contracts, and tests.
- `server/` contains the Python MCP server and dashboard.
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

## Manual state migration

These steps document a manual migration from the prior product state. They have not been run by this plan.

Renaming files does not upgrade the database schema. This server accepts schema 16. Fresh databases initialize directly to schema 16. On startup, the server automatically upgrades schema 15 databases. Read-only preflight checks reject unsupported schemas (<15 or >16) before writes. Preflight also rejects malformed JSON and invalid recognized metadata before writes. Any later migration failure triggers an atomic transaction rollback. Stop the daemon and back up the full state directory including sidecars. Downgrade requires restoring this pre-upgrade backup; older binaries reject schema 16. Raw historical counters are deleted during migration, not normalized. Server, plugin, and dashboard must deploy together as a unit. Select another state directory with `REFRACT_HOME` to start fresh without deleting history.

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

## Lineage

Refract 1.0.0 combines superpowers-ccg 12.0.0 and openmcp 2.0.0.
