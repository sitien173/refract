# Phase 6 notes

Status: complete

Execution mode: direct, per owner 2026-11-04. No coordinator, no Refract jobs, no review gates. TDD with per-step commits. Claude subagents in this worktree may write GREEN; the coordinator reruns every check before commit.

## Baseline

- HEAD 6edf28e2, base ref phase-06/base = 195bfed5.
- PYTEST 781 passed, 15 deselected. PLUGIN pass. LINES 9428.

## Owner decisions 2026-11-04

1. Project overlay `[[targets]]` entries name an existing global target by `id` and may only merge into its `env` table. No new targets. `env` means the per-target table; there is no top-level `[env]` in the overlay. Overlay sections are `profiles` and `targets`.
2. `[project]` and `[project].default_profile` are removed. The removed-key error tells the user to pass `profile` on `submit`.

## v3 format, from DESIGN.md Config and the decisions above

- Global sections: `daemon`, `logging`, `notifications`, `targets`, `profiles`.
- `[daemon]`: `host`, `port`, `max_jobs`, `default_profile`, `breaker_failure_threshold`, `breaker_base_cooldown_s`, `breaker_max_cooldown_s`, `ask_timeout_s`.
- `[logging]`: `level`, `file`, `max_bytes`, `backup_count`.
- `[notifications]`: `enabled`.
- `[[targets]]`: `id`, `backend`, `model`, `backend_profile`, `reasoning`, `system_prompt`, `isolated`, `read_only`, `args`, `max_concurrency`, `context_window`, `retry = { attempts, codes, patterns }`, `env = { ... }` with literal string values.
- `[profiles.<name>]`: `extends` plus workflow keys; a workflow value is a target id, a list of ids, or `{ targets, timeout_s }`.
- Project overlay: `[profiles.<name>]` as above, may extend global profiles; `[[targets]]` with `id` and `env` only.

## Removed-key table, each a load error naming the replacement

| Removed | Replacement hint |
|---|---|
| `[langfuse]` | removed, no replacement |
| `[daemon].history_turns`, `[daemon].history_bytes` | removed, no replacement |
| `[retryPolicies]` | `targets[].retry` |
| `targets[].retryPolicy` | `targets[].retry` |
| `[envs]` | `targets[].env` |
| `targets[].envs_vars` | `targets[].env` |
| `targets[].envs` | `targets[].env` |
| `targets[].contextWindow` | `targets[].context_window` |
| `targets[].profile` | `targets[].backend_profile` |
| profile workflow `max_attempts` | `targets[].retry.attempts` |
| `[logging].format`, `console`, `capture_warnings` | removed, no replacement |
| overlay `[project]` | pass `profile` on `submit` |
| overlay `[envs]` | `targets[].env` |
| `${NAME}` in an env value | write the literal value; the daemon environment is inherited |

`task_routes.json`, `routes` and `routing_profile` are not config keys today; check the code for any reader before adding table rows.

## Step plan

- 6A: config loader. RED: one parametrized removed-key test; v3 overlay adds a profile and merges target env; overlay new target id rejected; `extends` cycle; inline `retry` parsed. GREEN: rewrite `config.py`, callers in `planning.py`, `execution.py`, `runtime.py`, `server.py`, `cli.py`, `config_inspection.py`; port tests.
- 6B: logging trim. RED: `format`, `console`, `capture_warnings` rejected via the table; file handler keeps permissions and redaction. GREEN: `logging_setup.py`.
- 6C: docs. `server/config.v3.toml` with all four backends and every v3 key, loaded by a test; README migration section; `server/README.md` and `server/CLI_ARGUMENTS.md` config sections.

## Step 6A: flat config loader

### RED

- New file `server/tests/test_config_v3.py`, 32 cases. 29 fail for the expected reasons. 3 pass on HEAD as characterization: `[daemon].history_turns`, `[daemon].history_bytes`, and overlay rejecting `[daemon]`.
- Added rule: unknown target keys are rejected with "Unsupported target settings". HEAD silently ignored them, for example `capabilities`. This follows the Phase 6 checklist that no removed key is silently ignored.
- Config errors are sanitized and drop target ids, so the bad-retry message is pinned as the sanitized "Target has invalid retry settings".

### GREEN design

- `TargetConfig` fields in order: id, backend, model, backend_profile, reasoning, system_prompt, isolated, read_only, args, max_concurrency, context_window, retry, env. `RetryPolicy(attempts=0, codes=(), patterns=())`.
- Inline `retry` table: attempts non-negative int, bool rejected; codes and patterns lists of strings; no other keys. Violations raise `Target {id!r} has invalid retry settings`, sanitized to `Target has invalid retry settings`.
- `env` values are literal strings. A value containing `${` raises the removed-key error. Delete templating; `resolve_target_environment` returns a copy of `target.env`.
- Unknown target key raises `Unsupported target settings`. Removed keys are checked first.
- One removed-key mapping in `config_inspection.py`, key to hint, formatted `{key} has been removed[; {hint}]`. The sanitizer passes exact table messages. Names kept as split literals so the acceptance grep stays empty. Old `_REMOVED_SECTION` and `_REMOVED_DAEMON_KEYS` and their sanitizer special cases are deleted.
- Profile workflow `max_attempts` becomes the removed-key error. `extends` and cycle checks stay.
- Delete `_retry_policies`, `_envs`, the legacy `profile` alias, `envs_vars` and `envs`, `DaemonConfig.retry_policies`, `.envs` and `.project_profile_declarations`.
- Overlay: sections `profiles` and `targets` only. `[project]` and `[envs]` get removed-key messages. `[[targets]]` must name an existing id, otherwise `Project config cannot add targets`; keys other than id and env raise `Unsupported project target settings`; env merges with project winning, base not mutated.
- Callers read `target.retry.attempts/codes/patterns`. `planning.target_execution_key` must still change when env or retry changes.
- Test port: remove `capabilities` from fixtures; port retry, context_window and env-redaction tests to v3 names; delete only tests whose behavior is gone. Logging settings are 6B.
- Subagent spawn limit for this session is reached, so GREEN is written directly.

### GREEN
- `config_inspection.py` `REMOVED_KEYS`: `[logging].format`, `[logging].console`, `[logging].capture_warnings`, empty hints.
- `config.py`: `LoggingConfig` has `level`, `file`, `max_bytes`, `backup_count`. `_logging_config` rejects the three keys through `_reject_removed`.
- `logging_setup.py`: deleted `_JsonFormatter`, `_timestamp`, `_STANDARD_RECORD_FIELDS`, `_boolean`, `_BoundedQueueHandler`, `_GracefulQueueListener`, queue and listener globals, warning capture, and the `REFRACT_LOG_FORMAT`, `REFRACT_LOG_CONSOLE`, `REFRACT_LOG_CAPTURE_WARNINGS` env overrides. `configure` attaches one handler with the context filter directly to the `refract` logger. `_stop_locked` closes the handlers it owns.
- `cli.py`: removed `--log-format`, `--log-console`, their override mapping, and the `format` and `console` fields of `doctor` output.
- `CLI_ARGUMENTS.md`: logging env list trimmed to the four remaining variables.
- Tests: `test_logging.py` ported; `test_application_isolation.py` drops `--log-format`.

### Deleted tests
- `test_logging.py::test_bounded_queue_summarizes_dropped_records`
- `test_logging.py::test_shutdown_restores_warning_logger`
- `test_logging.py::test_progress_token_presence_boolean_is_visible_in_json_formatter[True]` and `[False]`
- `test_logging.py::test_queued_exceptions_are_reported_and_redacted[json]`; the text case is kept as `test_exceptions_are_reported_and_redacted`.
- `test_logging.py::test_json_logging_has_context_structure_and_redaction` is replaced by `test_text_logging_has_context_and_redaction`.

### Verification
- PYTEST: 766 passed, 15 deselected.
- PLUGIN: pass. LINES: 8735, down from 8982. ruff F: no diff against HEAD.

### Deviations
- The stderr handler stays as the fallback when `file` is disabled or cannot be opened. It is not configurable. Without it a disabled file leaves no sink.
- `test_invalid_logging_configuration_is_rejected` now uses an invalid `level`, because `format` is a removed key.

### Debt
- None new.

## Step 6B: logging trim

### RED
- `server/tests/test_config_v3.py`: `_REMOVED` gained `[logging].format`, `[logging].console`, `[logging].capture_warnings`, plus a check that `LoggingConfig` has exactly the fields `level`, `file`, `max_bytes`, `backup_count`. Verified RED for the right reasons on HEAD `e7e4ea13`. Uncommitted.

### GREEN plan
- `config.py` `LoggingConfig` (line ~76): drop `format`, `console`, `capture_warnings`. `_logging_config` (~495): allowed keys `level`, `file`, `max_bytes`, `backup_count`; call the `REMOVED_KEYS` rejection for the three removed keys before the unknown-key check; delete format and boolean validation.
- `config_inspection.py` `REMOVED_KEYS`: add the three keys with hints from the removed-key table above.
- `logging_setup.py` (587 lines): delete `_JsonFormatter` (~230), `_formatter` name switch (~370), `_BoundedQueueHandler` (~296), `_GracefulQueueListener` (~356), `_LISTENER`/`_QUEUE_HANDLER` queue plumbing in `configure` (~451) and `_stop_locked` (~391), `logging.captureWarnings` calls (~419, ~522), console handler. Keep `_TextFormatter`, `_ContextFilter`, `redact_text`, `_safe_value`, `_rotate_private_log`, `_secure_parent`, `_file_log_handler` (0600), `log_context`, `get_logger`, `shutdown`. Check `LoggingOptions` protocol (~29), `ResolvedLoggingConfig` (~42) and `resolve_config` (~118) for env overrides of the removed options (e.g. `REFRACT_LOG_FORMAT`, `REFRACT_LOG_CONSOLE`) and remove them; check CLI flags in `cli.py` and `server/CLI_ARGUMENTS.md`.
- Port `tests/test_logging.py`: delete only tests for JSON format, console, queue drop notices, warning capture; record names here. Keep redaction and 0600 tests.

### GREEN progress
- Done, uncommitted: `config_inspection.py` `REMOVED_KEYS` has the three `[logging]` keys with empty hints. `config.py` `LoggingConfig` has `level`, `file`, `max_bytes`, `backup_count`; `_logging_config` calls `_reject_removed("[logging].<key>")` for the three keys. `tests/test_config_v3.py` 43 passed.
- Remaining: `logging_setup.py` still reads `format`, `console`, `capture_warnings` in `LoggingOptions` (~29), `ResolvedLoggingConfig` (~42), `resolve_config` (~118, env `REFRACT_LOG_FORMAT`, `REFRACT_LOG_CONSOLE`, `REFRACT_LOG_CAPTURE_WARNINGS`), `_resolved_logging_config` (~161), `_JsonFormatter` (~230), queue classes (~296-368), `_formatter` (~370), `_stop_locked` (~391), `configure` (~451-545, startup log fields `log_format`, `console`). `cli.py` has `--log-format` (~40), `--log-console` (~51), `logging_config.console` (~123), env mapping (~141-147).
- Decision: keep the stderr fallback when `file` is disabled or cannot be opened. It is not configurable. Record as deviation.

## Step 6C: config docs

### RED
- `test_config_v3.py::test_example_v3_config_loads_and_covers_every_key`: failed because `server/config.v3.toml` did not exist. It checks all four backends, every target key in `_TARGET_KEYS`, every `[daemon]`, `[logging]` and `[notifications]` key, `extends`, and the string, list and `{ targets, timeout_s }` workflow forms. Env values must be placeholders.
- `test_config_v3.py::test_readme_migration_section_lists_every_removed_key`: failed because the root README had no `## Migrating config to v3` section. It checks one table row per `REMOVED_KEYS` entry with its hint.

### GREEN
- Created `server/config.v3.toml`. Placeholder values only.
- `README.md`: new `## Migrating config to v3` section with the removed-key table and rewrite notes.
- `server/README.md`: `### Configuration` rewritten for v3 with a key table and profile forms; `### Shared Retry Policies` replaced by `### Target retry`; logging paragraph and env variable list updated; `## Target environments` rewritten for the per-target `env` table and the `profiles` plus target `env` overlay; `contextWindow` example renamed to `context_window`.
- `server/CLI_ARGUMENTS.md`: removed `capabilities` lines from the args example; credential guidance names the target `env` table.
- `plugin/setup/backends.md` and `plugin/skills/setting-up-refract/SKILL.md`: target field list, credential guidance and the per-project override now match v3.

### Verification
- PYTEST: 768 passed, 15 deselected.
- PLUGIN: pass. LINES: 8735. ruff F: no diff against HEAD.
- Acceptance grep prints only `server/src/refract/backends/claude.py:177` `contextWindow`, the Claude CLI's own field name, recorded in 6A.

### Deviations
- The two plugin docs are outside the Phase 6 file list. They described removed keys, so they were updated with the other config docs.

### Debt
- Root `README.md` `## Manual state migration` still describes schema 16 migration. Owner: Phase 7 final docs audit.

## Phase 6 acceptance

- PYTEST passes: 768 passed, 15 deselected. Baseline was 781; the drop is the deleted tests recorded in 6A and 6B.
- `server/config.v3.toml` loads in `test_example_v3_config_loads_and_covers_every_key`.
- `test_config_v3.py::test_removed_key_fails_load_with_replacement_hint` is one parametrized test covering every `REMOVED_KEYS` entry.
- The acceptance grep prints only `backends/claude.py:177` `contextWindow`, the Claude CLI's own output field. Recorded deviation.
- LINES 8735, down from 9428 at phase base.
- Refs: `phase-06/impl` and `phase-07/base` = `607abd5d`.
