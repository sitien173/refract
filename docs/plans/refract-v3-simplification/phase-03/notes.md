# Phase 3 notes

Status: complete. Tasks 3A through 3E are committed; see each section.

## Task 1: transport cancel signal

RED: not meaningful. Swapping `threading.Event` for `asyncio.Event` does not change observable behavior, because both expose `is_set()`. The existing cancel test covers the retained behavior.

GREEN: `server/tests/test_transport.py` 12 passed with `-W error::pytest.PytestUnraisableExceptionWarning`.

Changes:
- `backends/_process.py`: `cancel` is `asyncio.Event | None`. `threading` import removed. `_Tail` renamed `OutputTail` for use by backend parsers. Prompt is UTF-8 encoded before spawn; an encode error returns `request_fatal` without starting the child. stdin failures use `_stdin_outcome`.
- `tests/test_transport.py`: cancel test uses `asyncio.Event`; `threading` import removed.

Decision: `OutputTail` keeps the newest line even when it exceeds 64 KiB, as recorded in phase-02 notes.

Full suite after the change: 1097 passed, 15 deselected. Plugin scripts exit 0.

## Open for the next pass

- Migrate `claude.py`, `codex.py`, `pi.py`, `agy.py` onto `run_process` through a per-run parser with `feed` and `outcome`.
- Delete `backends/_shell.py`, `StreamBridge` in `drivers.py`, and `asyncio.to_thread` in `drivers.py`. Adjust `execution.py` drain path.
- Rewrite the 145 `run_shell_command` patch sites in `tests/test_smoke.py`, `tests/test_streaming_backends.py`, and `tests/test_execution.py`.
- Codex: no agent message is `request_fatal`; delete the cwd session guess and the sessions-tree rglob.
- pi: prompt on stdin, argv prompt removed. agy: argv prompt, `request_fatal` above 102400 bytes.
- Recovery: delete the reconstruct phase and history rebuild. Config `history_turns` and `history_bytes` fail load.

## Task 3A: async driver path, shared helpers, claude

RED:
- The claude characterization set was first run against the unchanged sync `execute`: 9 passed. The pinned values were fixed from that run, then the file moved to the parser API.
- The new and migrated tests (`test_claude_backend.py`, `test_smoke.py`, `test_streaming_backends.py`, `test_execution.py`, `test_ask.py`) run against the `HEAD` source: 45 failed, 280 passed. `test_backend_common.py` failed collection because `refract.backends._common` did not exist.

GREEN:
- Full suite: 1115 passed, 15 deselected.
- `plugin/tests/test-session-start.sh`, `test-contracts.sh`, `test-stats.sh`: exit 0.
- `git grep -nE '_shell|threading|to_thread' -- server/src/refract/backends/claude.py`: no match.
- Differential parity: `HEAD` sync `execute` and the new `ClaudeRun` fed 6 line sets in stream and json modes (12 cases). Results, telemetry, and emitted events are identical after removing `observed_at` wall-clock values.

Interface for 3B and 3C:

```python
# backends/__init__.py
AsyncEventHandler = Callable[[dict[str, Any]], Awaitable[None]]

# backends/<name>.py
async def execute(
    params: BackendParams,
    *,
    cancel: asyncio.Event | None = None,
    on_event: AsyncEventHandler | None = None,
) -> BackendResult: ...

class <Name>Run:
    def __init__(self, params: BackendParams, on_event: AsyncEventHandler | None) -> None: ...
    async def feed(self, line: str) -> None: ...
    def outcome(self, process: ProcessOutcome) -> BackendResult: ...
```

- `on_event` set selects stream output. `None` selects the non-streaming output format.
- `cancel` set kills the child through `run_process`. The run maps it to `cancelled`.
- `execute` runs `preflight`, builds argv inline, calls `run_process(cmd, params.PROMPT, params.env, cwd, deadline, cancel, run.feed)`, then returns `run.outcome(process)`.

Decisions:
- `drivers.py`: `_ASYNC_BACKENDS = frozenset({"claude"})`. Async backends are awaited directly. A 50 ms poll copies the thread-safe `threading.Event` into an `asyncio.Event`. Other backends keep `to_thread` and `StreamBridge` until 3D.
- `DriverRegistry.execute` takes an `on_event` keyword. `execution.py` passes `consume` when streaming is supported. `consume` holds the body that the bridge drain used. Both paths share it. `has_tool_activity` also reads a `consumed_tool_activity` flag set by `consume`.
- `telemetry.py`: `TelemetryAccumulator.has_consumption_or_context()` replaces the claude reads of `_has_any_consumption` and `_context_used_tokens`.
- `backends/_common.py` holds only what claude uses: `as_int`, `parse_token_component`, `TokenUsage`, `read_usage`. Token input is `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. A malformed component makes input `None` and marks the usage observed. `pi.py` and `agy.py` keep their copies until 3B and 3C.
- `ClaudeRun` keeps bounded state only: the final `result` fields, the session and model values, the token accumulator, and at most `MAX_DIAGNOSTICS` = 50 diagnostic lines. The first fatal-token line is kept even beyond that bound, so classification matches an unbounded run. No raw lines are retained.
- Timeout text stays `claude subprocess timed out after {timeout_s}s`, the format the old `consume_stream` produced.
- Tests: `tests/claude_cli.py` provides `stub_claude`. It installs a fake `claude` launcher on the `shutil.which` path, and the launcher runs `tests/fixtures/fake_cli/fake_claude.py`. `feed_claude` and `drive_claude` drive the parser directly. The `run_shell_command` patches for claude are gone.
- `tests/test_live_backends.py`: `test_live_claude_execute` now awaits the async call. The live tests are deselected and were not run.

Deviations:
- DESIGN.md lists a separate `argv(request)` method. 3A does not add it. argv stays inline in `execute`. 3B and 3C should follow the inline form unless 3D extracts `argv` for all four backends.
- A failing `on_event` sink on the claude path becomes a `FATAL` `execution_error` result whose text is `RuntimeError: sink failed`, the format `run_process` uses for `on_line` failures, which `test_transport.py` pins. The bridge path raised the exception from the drain task instead.

Risks:
- The live claude CLI was not run in this step.
- Cancel reaches the claude child up to 50 ms after the threading event is set.
- The claude path is the only async path until 3B. The drain and `StreamBridge` code stays for pi, agy, and codex until 3D.

## Task 3B: pi and agy on the async path

RED:
- The pi and agy test files `tests/test_pi_backend.py` and `tests/test_agy_backend.py` ran against the `HEAD` source: 4 failed, 23 passed. The failures are the intended ones:
  - `test_prompt_is_sent_on_stdin_not_argv`: the prompt text appears in argv.
  - `test_prompt_over_100_kib_fails_before_spawn`: `SUCCESS`, expected `REQUEST_FATAL`. The process was spawned.
  - `test_prompt_limit_counts_utf8_bytes_not_characters`: `warning`, expected `request_fatal`.
  - `test_non_utf8_output_does_not_truncate_later_lines`: `RETRYABLE`, expected `SUCCESS`. The strict decode dropped later lines.
- Parsed-outcome characterization for pi and agy covers text, session id, errors, tokens, model, and precedence. It passed on `HEAD` before the parser change.

GREEN:
- `test_pi_backend.py` and `test_agy_backend.py`: 27 passed.
- Full suite: 1142 passed, 15 deselected.
- `plugin/tests/test-session-start.sh`, `test-contracts.sh`, `test-stats.sh`: exit 0.
- `git grep -nE '_shell|threading|to_thread' -- server/src/refract/backends/claude.py server/src/refract/backends/pi.py server/src/refract/backends/agy.py`: no match.

Decisions:
- `pi.py` and `agy.py` expose `execute(params, *, cancel, on_event)` and a `PiRun` or `AgyRun` with `async feed(line)` and `outcome(process)`. Both names are in `drivers._ASYNC_BACKENDS`. Codex stays on the thread path until 3C.
- `pi` sends the prompt on stdin through `run_process`. Its argv is otherwise unchanged. The CLI reads piped stdin in non-TTY mode, based on source evidence only. No live run was made.
- `agy` keeps the prompt in argv. The check counts UTF-8 bytes of `PROMPT`. A prompt above 102400 bytes returns `request_fatal` before spawn. A prompt that cannot be encoded as UTF-8 also returns `request_fatal`. The driver maps `request_fatal` to `REQUEST_FATAL` in `_normalize`.
- `agy` output uses `run_process` with its replacing decoder. The strict decode path is gone.
- `_common.py` gains `is_fatal_line`, `tool_started`, and `EventBuffer`, which `pi` and `agy` both use. `as_int` and `read_usage` remain there. `_event_model` stays per backend because pi and agy read different payload shapes. Their names match, but the logic does not.
- `TelemetryAccumulator.context_used_tokens()` is the public read for agy. `pi` and `agy` no longer read private telemetry fields.
- `pi` emits through `EventBuffer`. The sync `emitter` path is no longer used by either backend.
- Test helpers: `tests/cli_stub.py` provides `execute_sync`, which runs an async `execute` and mirrors `params.cancel_event`. It also provides `fake_run_process` and `shell_fake_as_process`. The second adapts the old `run_shell_command` generator fakes to `run_process`. It maps `TimeoutExpired` to `timeout` and `ShellCommandFailed` to `execution_error`, matching `_process.py`.
- `tests/fixtures/fake_cli/fake_claude.py` is now `fake_cli.py`. The claude stub delegates to the generic module.

Deviations:
- The 3B differential parity check against the HEAD sync implementations was not run. The characterization tests cover the parsed outcomes instead.
- Pi argv assertions in `test_smoke.py` no longer end with the prompt. The prompt check lives in `test_pi_backend.py`.
- Cancel tests for pi pass `cancel=asyncio.Event` directly to `execute`, the same pattern as the claude cancel test.

Risks:
- Pi stdin behavior is verified from source only. A live `pi` run was not made, and the live tests are deselected.
- Test helpers poll cancel every 10 ms. The production driver polls every 50 ms.

## Task 3C: codex on the async path

RED:
- `tests/test_codex_backend.py` ran against the `HEAD` source in a scratch copy outside the repo: 4 failed, 13 passed. The 13 passing tests pin existing parsed outcomes.
- The four failures:
  - `test_exit_zero_without_agent_message_is_request_fatal_and_never_returns_jsonl`: `SUCCESS`, expected `REQUEST_FATAL`. The raw stream was returned as the answer.
  - `test_blank_last_message_without_agent_message_is_request_fatal`: `SUCCESS`, expected `REQUEST_FATAL`.
  - `test_fatal_token_in_diagnostic_without_agent_message_is_fatal_backend`: `SUCCESS`, expected `TARGET_FATAL`.
  - `test_resume_without_exact_session_source_stores_no_session_id`: `66666666-777...-aaaaaaaaaaaa` stored, expected empty. No exact source existed, so the stored id came from a guess.

GREEN:
- `tests/test_codex_backend.py`: 17 passed on the migrated tree.
- Full suite: 1157 passed, 15 deselected. The 1142 baseline changed because the guess-fallback tests were removed and the characterization tests were added.
- `plugin/tests/test-session-start.sh`, `test-contracts.sh`, `test-stats.sh`: exit 0.
- `git grep -nE '_shell|threading|to_thread|rglob' -- server/src/refract/backends/{claude,pi,agy,codex,codex_rollout}.py`: no match.
- No file under `server/src/refract/backends/` imports `_shell` except `_shell.py` itself.
- Lint: `ruff check` reports the same 10 findings as `HEAD`. The codex findings moved with the collector into `codex_rollout.py`.

Decisions:
- `codex_rollout.py` holds `_CodexRolloutCollector` as a pure move. Its class body is unchanged from `HEAD`.
- Session id sources, in order: `thread.started`, the session line in the last-message file, the `session id:` line on stdout. The first exact value wins. No value returns an empty id.
- The collector's exact rollout lookup stays. It walks `CODEX_HOME/sessions` with bounded `os.scandir` under `MAX_DISCOVERY_DEPTH` and `MAX_DISCOVERY_ENTRIES`. It needs a session id that is already known, so it cannot create one. It matches the file name and the header identity. It does not use `rglob`.
- The cwd-only guess and the whole-tree `rglob` guess are deleted, with their tests.
- Answer: last-message file text when non-empty, else the joined `agent_message` items. An empty answer with no fatal token returns `request_fatal` with message `no agent message`. Raw stdout is never returned.
- Diagnostics keep the first 50 non-JSON lines and the first fatal-token line. They are used only when the run produced no agent output.
- `read_and_unlink` moves to `_common.py` with an `errors` argument. codex passes `replace` and agy passes `ignore`, as before.
- `CodexRun` holds bounded state. It keeps no raw lines and rejoins no stdout. Its `feed` is async and flushes `EventBuffer` after each line.
- Telemetry: codex reads only public `TelemetryAccumulator` methods. `HEAD` had three private reads, and `has_consumption_or_context()` and `snapshot()` replace them.
- The prompt stays on stdin. The resume argv is unchanged.
- `codex` is added to `drivers._ASYNC_BACKENDS`. All four registered backends are now async. The `to_thread` branch remains for step 3D.
- Test helpers: `tests/fixtures/fake_cli/fake_cli.py` and `tests/cli_stub.py` accept a `last_message` value and write it to the `-o` path.

Deviations:
- Twelve streaming tests, the `test_execution.py` budget test, and smoke tests whose fixtures had no agent message would have passed only through the removed raw-stdout fallback. Each fixture now ends with an `agent_message` item, or `FINAL_AGENT_MESSAGE` in `test_streaming_backends.py`. Their assertions are unchanged.
- The `_EventParser` test in `test_execution.py` now drives `CodexRun.feed` with the runtime `on_event` sink.
- Codex tests patch `run_process` through `shell_fake_as_process`. The characterization file runs through `run_target` and the stub CLI.
- No live `codex` run was made.

Risks:
- Stream shapes follow the existing fixtures and the stub. A recorded live `codex` session was not checked.
- The bounded rollout walk can miss a session file beyond its depth or entry limit. Context then stays estimated.
- The `thread.started` id on resume is assumed to match the session id. Not verified live.

## Task 3D: remove the thread path

RED: not meaningful. All four backends were already async after 3C, so the `to_thread` branch and `StreamBridge` were unreachable from production. Existing stream, cancel, and telemetry tests in `test_execution.py` cover the retained behavior after their fakes moved to `on_event`.

GREEN:
- Full suite: 1147 passed, 15 deselected. The 1157 baseline dropped by 10 deleted tests: 5 `StreamBridge` unit tests, 4 `_shell` transport tests in `test_smoke.py`, and `test_processes.py`. `test_transport.py` covers nonzero exit, cancel, timeout, and stdin for `run_process`.
- `git grep -nE '_shell|StreamBridge|to_thread|_ASYNC_BACKENDS' -- server/src/refract/drivers.py server/src/refract/execution.py server/src/refract/backends`: no match.
- `ruff check` on the touched files: same findings as `HEAD`.

Changes:
- `backends/_shell.py` deleted.
- `drivers.py`: `StreamBridge`, `_ASYNC_BACKENDS`, the `to_thread` branch, and the `emitter` keyword removed. Every backend runs through `_run_async_backend`.
- `execution.py`: bridge and drain task removed. The recorder flush that ended the drain now runs in the invocation `finally`. Tool activity comes only from `consume`.
- `tests/test_ask.py`: the env-injection test runs `run_process` instead of `stream_shell_command_lines`.
- `tests/cli_stub.py`: defines `ShellCommandFailed` for `shell_fake_as_process` fakes. `run_target` passes only `on_event`.
- `tests/test_execution.py`: fake drivers take `on_event` and await it. Thread workers became coroutines.

Debt:
- `BackendParams.emitter` has no production reader. Test helpers `execute_sync` and `drive_claude` still use it as the event sink at about 45 call sites. Owner: Phase 4 or consolidation.
- `cancel_event` stays a `threading.Event` subclass (`scheduler.CancelEvent`). `drivers._mirror_cancel` copies it into an `asyncio.Event` with a 50 ms poll.

## Task 3E: remove in-run recovery

Owner decision, 2026-11-04: remove in-run recovery completely. No reconstruct step and no fresh restart on the same target. A resumed `context_overflow` is a plain failure with `failure_kind` `context_overflow`; the coordinator resubmits with `fresh_session=true`. A failure after tool activity stays `replay_blocked`. PLAN.md Phase 3 task 3 and acceptance, and DESIGN.md flow item 3 and the errors table, now say this.

RED, run against `HEAD` `37108b99`:
- `test_config.py::test_removed_history_settings_fail_load[history_turns|history_bytes]`: failed; both keys loaded without error.
- `test_execution.py::test_resumed_context_overflow_fails_without_in_run_recovery`: failed; `HEAD` ran a reconstruct call and succeeded.
- `test_execution.py::test_sessionless_job_sends_prompt_without_history`: failed; `HEAD` prefixed stored history to the prompt.
- `test_execution.py::test_resumed_failure_after_tool_activity_is_replay_blocked`: characterization, passed on `HEAD` and after.

GREEN:
- Full suite: 1126 passed, 15 deselected. The 1147 baseline dropped by 25 deleted tests and gained 4 new ones.
- PLUGIN: session-start, contracts, and stats tests passed.
- `git grep -nE 'reconstruct|history_turns|history_bytes|context_turns' -- server/src`: only `context_turns` schema DDL and schema validation in `database.py`.
- `git grep -nE 'accumulator\._' -- server/src/refract/backends`: no match.
- `ruff check --select F` on touched files: no new findings. `tests/test_retention.py` `dataclasses.replace` F401 is pre-existing.
- LINES: 12009.

Changes:
- `execution.py`: one `_run_target_invocation` per attempt. `_TargetAttempt.recovered`, `recovery_phase`, `_ExecutionContext.effective_prompt`, `_with_history`, `_can_recover`, `_record_recovery_result`, and `_store_turn` deleted. A `context_overflow` result still emits `target.context_overflow`. `target.session_recovery_*` events are no longer emitted. Success stores only the session ID through `Database.store_session`.
- `database.py`: `append_turn`, `recent_turns`, `context()`, and the `history_turns` constructor argument deleted. `store_session` added. `finish_fresh_job_success` no longer takes `prompt` and no longer writes a turn. `prune_history` no longer touches `context_turns`.
- `models.py`: `ContextStreamView` deleted. `runtime.py`: `Database(config.database_path)`.
- `config.py`: `history_turns` and `history_bytes` raise `[daemon].<key> has been removed`. `config_inspection.py` allow-lists those two messages, otherwise the sanitizer reports `Invalid configuration`.

Deleted tests, 25: 19 `test_recovery_*` and recovery-specific tests in `test_execution.py` that pinned reconstruct or fresh phases, history bytes, recovery events, or recovery invocation identity; `test_retry_recovery_to_transient_to_success`; `test_retry_cancellation_during_recovery_bookkeeping_prevents_invocation`; `test_standard_sessionless_reconstructs_history_while_fresh_bypasses`; `test_database.py` `context()` query-count and turn-rollback tests; `test_retention.py::test_turn_retention_caps_each_context_and_role`.

Adapted tests, assertions moved from turns to sessions: schema-15 reopen and migration, fresh-success atomicity, fresh-job persistence rollback with the trigger moved to `context_sessions`, fresh-job state-update failure, `test_other_job_plan_and_context_retain_role`, `test_retry_sequential_streams_and_ask_tokens`, and the storage-fault case of `test_retry_finalization_faults_release_target_resources`. The `clear_sessions` test now goes through `finish_fresh_job_success`, because `store_session` has no `clear_sessions` flag.

Deviations:
- The first edit dropped the cancel check between attempt setup and the driver call. `test_retry_cancellation_during_attempt_setup_prevents_driver_invocation` caught it, and the check is restored.

Debt:
- `test_telemetry.py::test_session_recovery_invocations` exercises the accumulator across invocations. Production now always passes `invocation=1`. Kept; owner: Phase 4 or consolidation.
- `context_turns` stays in the schema and in schema validation until the Phase 5 storage change.
