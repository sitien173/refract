# Refract backends

Operator reference for `setting-up-refract`. Refract accepts exactly four
`backend` values; the daemon resolves each through `PATH`.

| `backend` | Detect | List models | `reasoning` becomes | `isolated` / `read_only` |
| --- | --- | --- | --- | --- |
| `agy` | `command -v agy` | `agy models` | ignored; pick a model variant whose name carries the level, e.g. `"Gemini 3.1 Pro (High)"` | not supported |
| `codex` | `command -v codex` | no listing command; ask the user, or omit `model` to use the Codex default | `-c model_reasoning_effort=<value>` | not supported |
| `pi` | `command -v pi` | `pi --list-models` | `--thinking <value>` | supported |
| `claude` | `command -v claude` | aliases such as `opus`, `sonnet`; see `claude --help` | `--effort <value>` | supported |

Valid `reasoning` values belong to each CLI; confirm them in its `--help`
before writing them.

- `isolated = true` strips context files, extensions, plugins, hooks, and MCP
  servers from the worker.
- `read_only = true` limits the worker to read and search tools.
- `system_prompt` is passed to `pi` and `claude`.

## Target fields

`id` and `backend` are required. Optional: `model`, `reasoning`,
`system_prompt`, `isolated`, `read_only`, `args`, `max_concurrency`,
`contextWindow`, `retryPolicy`, `envs_vars`, `envs`. Credentials stay in each
CLI's own store or in `[envs.<name>]`, never in `args`: target settings are
snapshotted into job records.

## Profile fields

A profile maps workflows `implement`, `review`, `consult`, and `other` to a
target id or an ordered list of ids; later ids are fallbacks. `extends`
inherits another profile. `other` never falls back and needs an explicit
mapping. `[daemon].default_profile` must name a declared profile.

## Full reference

- Configuration examples, environments, retry policies:
  <https://github.com/sitien173/refract/blob/main/server/README.md>
- Per-backend CLI flags:
  <https://github.com/sitien173/refract/blob/main/server/CLI_ARGUMENTS.md>
