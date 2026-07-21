# OpenMCP configuration reference

Global config: `~/.openmcp/config.toml` (relocate with `OPENMCP_HOME`).

## Selection model

- **Workflow:** `implement`, `review`, or `consult`.
- **Profile:** maps workflows directly to targets.
- **Target:** backend/model execution configuration.

A profile value may be:

```toml
implement = "forge-primary"
implement = ["forge-primary", "forge-backup"]
implement = { targets = ["forge-primary", "forge-backup"], max_attempts = 2, timeout_s = 600 }
```

Target lists are ordered for failover.

## `[daemon]`

| Key | Default | Purpose |
| --- | --- | --- |
| `host` | `127.0.0.1` | Listener host; keep on loopback. |
| `port` | `8765` | Listener port. |
| `max_jobs` | `4` | Concurrent job workers. |
| `history_turns` | `8` | Context turns retained per lane. |
| `history_bytes` | `65536` | Context byte budget per lane. |
| `default_profile` | `balanced` | Profile used when submission omits one. |

Host, port, worker, history, and home changes require a daemon restart.

## `[logging]`

| Key | Default | Purpose |
| --- | --- | --- |
| `level` | `INFO` | Log level. |
| `format` | `text` | `text` or newline-delimited `json`. |
| `file` | `openmcp.log` | Relative paths resolve under `OPENMCP_HOME`; `false` disables. |
| `console` | `false` | Mirror logs to stderr. |
| `max_bytes` | `10485760` | Rotation size. |
| `backup_count` | `5` | Rotated files retained. |
| `capture_warnings` | `true` | Send Python warnings to logs. |

Logging changes require restart. Environment overrides are
`OPENMCP_LOG_LEVEL`, `OPENMCP_LOG_FORMAT`, `OPENMCP_LOG_FILE`,
`OPENMCP_LOG_CONSOLE`, `OPENMCP_LOG_MAX_BYTES`,
`OPENMCP_LOG_BACKUP_COUNT`, and `OPENMCP_LOG_CAPTURE_WARNINGS`.

## Targets `[[targets]]`

Targets are global only.

| Field | Default | Purpose |
| --- | --- | --- |
| `id` | required | Unique target identifier. |
| `backend` | required | `agy`, `codex`, or `pi`. |
| `model` | CLI default | Backend model. |
| `backend_profile` | CLI default | Codex named profile (`-p`). |
| `reasoning` | CLI default | Reasoning/thinking effort. |
| `system_prompt` | empty | Backend system prompt. |
| `isolated` | `false` | Disable ambient project resources for Pi. |
| `read_only` | `false` | Restrict Pi to `read,grep,find,ls`. |
| `args` | `[]` | Additional argv tokens. |
| `capabilities` | all built-ins | Used to derive the built-in profile when profiles are absent. |
| `max_concurrency` | `1` | Simultaneous jobs allowed on the target. |

Capability conventions are `code`, `review`, `consult`, and `reasoning`.
Explicit profile mappings select the named target directly.

## Profiles `[profiles.<name>]`

Every profile maps all built-in workflows:

```toml
[profiles.balanced]
implement = ["forge-primary", "forge-backup"]
review = "sentinel-primary"
consult = "sage-primary"
```

A string selects one target. A list provides ordered failover. An inline table
supports:

| Field | Default | Purpose |
| --- | --- | --- |
| `targets` | required | Target ID or ordered target ID list. |
| `max_attempts` | number of targets | Maximum target attempts. |
| `timeout_s` | `0` | Per-attempt timeout; `0` disables it. |

## Project overrides `<project>/.openmcp/config.toml`

Projects override profiles only. Targets and daemon settings remain global.

```toml
[project]
default_profile = "quality"

[profiles.quality]
review = "strict-reviewer"
```

Unspecified workflow mappings inherit from the same global profile, or from the
global default when defining a new profile. Precedence is explicit submission,
project config, global config, then built-in defaults.

## Local overlays `<project>/.openmcp.local.toml`

```toml
[[overlays]]
include = ["config/*.development.json"]
exclude = ["config/private.development.json"]
workflows = ["implement"]
```

Every match must be Git-ignored. Paths cannot contain symlinks. Use relative
globs and `exclude`, not negated patterns. Never expose secrets. Overlay changes
are copied back only during `job_integrate` after hash verification.

## `task_guide.json`

Task guidance is read on every `task_guide` call:

```json
{
  "version": 1,
  "columns": ["use_case", "workflow", "profile", "reason"],
  "recommendations": [
    {
      "use_case": "Repository implementation",
      "workflow": "implement",
      "profile": "quality",
      "reason": "Use quality execution."
    }
  ]
}
```

The coordinator passes `workflow` and optional `profile` to `job_submit`.
Recommendations should not contain target IDs or provider names.

## Reload behavior

`reload` validates and activates global targets, profiles, and target arguments
for subsequent submissions. Running jobs retain their immutable plans. Project
profiles and task guides reload when used.

`restart_required` reports static changes such as host, port, worker count,
history, home, or logging.

## CLI argument policy boundary

Every `args` item is one argv token launched without shell parsing. Do not
repeat first-class target fields in `args`.

Rejected for every backend:

- `--`

Rejected for Codex:

- `--cd`, `-C`, and attached-value forms

Rejected for isolated Pi:

- `--extension`, `-e`, `--skill`, `--prompt-template`, and `--flag=value`
  variants

Options that disable persistence, such as Codex `--ephemeral` or Pi
`--no-session`, prevent later context resumption. See `CLI_ARGUMENTS.md` for the
full backend flag reference.
