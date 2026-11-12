# Refract backends

Operator reference for `setting-up-refract`. Refract accepts exactly four
`backend` values; the daemon resolves each through `PATH`.

| `backend` | Detect | List models | `reasoning` becomes |
| --- | --- | --- | --- |
| `agy` | `command -v agy` | `agy models` | ignored; pick a model variant whose name carries the level, e.g. `"Gemini 3.1 Pro (High)"` |
| `codex` | `command -v codex` | no listing command; ask the user, or omit `model` to use the Codex default | `-c model_reasoning_effort=<value>` |
| `pi` | `command -v pi` | `pi --list-models` | `--thinking <value>` |
| `claude` | `command -v claude` | aliases such as `opus`, `sonnet`; see `claude --help` | `--effort <value>` |

Valid `reasoning` values belong to each CLI; confirm them in its `--help`
before writing them.

- `system_prompt` is passed to `pi` and `claude`.
- To isolate a `pi` worker from context files, extensions, skills, and prompt
  templates, set `args = ["--no-context-files", "--no-extensions",
  "--no-skills", "--no-prompt-templates"]`. Add `"--tools",
  "read,grep,find,ls"` to limit it to read and search tools.
- To isolate a `claude` worker from CLAUDE.md, plugins, hooks, and MCP servers,
  set `args = ["--safe-mode", "--strict-mcp-config"]`. Add `"--tools",
  "Read,Grep,Glob"` to limit it to read and search tools.

## Target fields

`id` and `backend` are required. Optional: `model`, `backend_profile`,
`reasoning`, `system_prompt`, `args`,
`max_concurrency`, `context_window`, `retry`, `env`. Credentials stay in each
CLI's own store or in the target `env` table, never in `args`: target settings
other than `env` are snapshotted into job records.

## Profile fields

A profile maps workflows `implement`, `review`, `consult`, and `other` to a
target id or an ordered list of ids; later ids are fallbacks. `extends`
inherits another profile. `other` never falls back and needs an explicit
mapping. `[daemon].default_profile` must name a declared profile.

## Full reference

- Configuration examples, environments, target retry:
  <https://github.com/sitien173/refract/blob/main/server/README.md>
- Per-backend CLI flags:
  <https://github.com/sitien173/refract/blob/main/server/CLI_ARGUMENTS.md>
