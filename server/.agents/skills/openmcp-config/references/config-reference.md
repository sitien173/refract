# OpenMCP configuration reference

Global config file: `~/.openmcp/config.toml` (relocate with `OPENMCP_HOME`).

## Table of contents

- [daemon]
- [logging]
- Targets
- Routes
- Routing profiles
- Project overrides
- Local overlays
- task_routes.json
- CLI argument policy boundary

## [daemon]

| Key | Default | Purpose |
| --- | --- | --- |
| `host` | `127.0.0.1` | Listener host. Keep on loopback. |
| `port` | `8765` | Listener port. |
| `max_jobs` | `4` | Concurrent job workers. |
| `history_turns` | `8` | Context turns retained per lane. |
| `history_bytes` | `65536` | Context byte budget per lane. |
| `default_routing_profile` | `balanced` | Profile used when a submission omits one. |

Host, port, worker, and history-limit changes require a daemon restart. Moving
`OPENMCP_HOME` also requires starting a new daemon process.

## [logging]

| Key | Default | Purpose |
| --- | --- | --- |
| `level` | `INFO` | Log level. |
| `format` | `json` | `text` or newline-delimited `json`. |
| `file` | `openmcp.log` | Relative paths resolve under `OPENMCP_HOME`; `false` disables the file sink. |
| `console` | `false` | Mirror logs to stderr. |
| `max_bytes` | `10485760` | Rotation size. |
| `backup_count` | `5` | Rotated files retained. |
| `capture_warnings` | `true` | Route Python warnings into logs. |

Logging changes require a restart. The MCP `reload` tool reports changed static
settings in `restart_required`. Environment overrides: `OPENMCP_LOG_LEVEL`,
`OPENMCP_LOG_FORMAT`, `OPENMCP_LOG_FILE` (`-`/`off`/`none` disables),
`OPENMCP_LOG_CONSOLE`, `OPENMCP_LOG_MAX_BYTES`, `OPENMCP_LOG_BACKUP_COUNT`,
`OPENMCP_LOG_CAPTURE_WARNINGS`. Prompts and model responses are never logged.

Global targets, routes, routing profiles, and target `args` can be validated and
activated for subsequent submissions with the MCP `reload` tool. Running jobs
retain their immutable execution plans. Invalid configuration does not replace
the active catalog.

## Targets `[[targets]]`

Targets own all provider execution settings. They are global only.

| Field | Default | Purpose |
| --- | --- | --- |
| `id` | required | Unique target identifier. |
| `backend` | required | `agy`, `codex`, or `pi`. |
| `model` | CLI default | Translated to the backend model flag. |
| `profile` | CLI default | Codex named profile (`-p`). |
| `reasoning` | CLI default | Reasoning/thinking effort. |
| `system_prompt` | empty | Backend system prompt. |
| `isolated` | `false` | Disable ambient project resources (Pi). |
| `read_only` | `false` | Restrict to read tools (Pi: `read,grep,find,ls`). |
| `args` | `[]` | Extra argv tokens for options without a first-class field. |
| `capabilities` | `["code","reasoning","review","consult"]` | Capabilities this target serves. |
| `max_concurrency` | `1` | Max simultaneous jobs on this target. |
| `priority` | `100` | Lower is preferred within a route pool. |

Capability convention: `code` for implementers, `review` for reviewers,
`consult`/`reasoning` for consultants. A route's `requires` must be a subset of
each pooled target's `capabilities`, or load fails.

## Routes `[[routes]]`

| Field | Default | Purpose |
| --- | --- | --- |
| `id` | required | Unique route identifier. |
| `requires` | `()` | Capabilities every pooled target must hold. |
| `targets` | required | Ordered target ID pool. |
| `max_attempts` | `2` | Attempts before the route fails. |
| `timeout_s` | `0` | Per-route timeout; `0` disables it. |

## Routing profiles `[routing_profiles.<name>]`

Maps logical roles onto route IDs. Map all three roles:

```toml
[routing_profiles.balanced]
implement = "forge"
review = "sentinel"
consult = "sage"
```

Add distinct profiles for cost, quality, latency, or offline policy. Two roles
may point at the same route.

## Project overrides `<project>/.openmcp/config.toml`

Projects override routes and profiles only, never targets or daemon settings.

```toml
[project]
default_routing_profile = "quality"

[[routes]]
id = "review-project"
targets = ["sentinel-primary"]

[routing_profiles.quality]
review = "review-project"
```

Precedence: explicit submission profile > project config > global config >
built-in defaults. Commit project config before registration or submission.

## Local overlays `<project>/.openmcp.local.toml`

Expose Git-ignored files to specific workflows.

```toml
[[overlays]]
include = ["config/**/*.development.json"]
exclude = ["config/private.development.json"]
workflows = ["implement"]
```

Rules: every matched file must already be Git-ignored; no symlinks in paths;
relative globs only; use `exclude`, not negated patterns; never expose secrets.
Overlay files copy into job worktrees and are written back on `job_integrate`
after hash verification. Concurrent local edits cause an integration conflict.

## task_routes.json

Guidance template read by the coordinator; does not route jobs itself. Reloads
on every `task_route` call.

```json
{
  "version": 1,
  "columns": ["use_case", "recommend", "role", "reason"],
  "routes": [
    {
      "use_case": "Non-UI repository implementation",
      "recommend": "Forge",
      "role": "owner",
      "reason": "Owns non-UI implementation."
    }
  ]
}
```

## CLI argument policy boundary

`args` items are individual argv tokens launched with `shell=False`. OpenMCP owns
the transport, workspace, prompt, output capture, and session arguments and
compiles first-class fields into backend flags. Do not duplicate first-class
fields or transport-owned options in `args`.

Rejected in `args` for every backend:

- The end-of-options terminator `--`.

Rejected for Codex:

- `--cd` and `-C` (and attached-value forms) - a target must not leave its
  isolated worktree.

Rejected for isolated Pi targets:

- `--extension`, `-e`, `--skill`, `--prompt-template` (and `--flag=value`
  forms) - isolation disables ambient resources.

Avoid options that disable persistence (Codex `--ephemeral`, Pi `--no-session`);
they prevent OpenMCP from resuming the backend context on a later job.

OpenMCP always enables the non-interactive approval mode per backend: Agy
`--dangerously-skip-permissions`, Codex `--yolo`, Pi `--approve` (or
`--no-approve` for isolated targets). Normal Pi targets get `--approve` appended
after `args` so target ordering cannot disable approval; Pi runs with
`--mode json` placed after `args` so output parsing cannot be replaced.

See the repository `CLI_ARGUMENTS.md` for the full per-backend flag tables.
