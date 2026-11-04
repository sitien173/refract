# Phase 2 notes

Status: partial. The transport layer is done and tested. Backend migration, `StreamBridge`, `to_thread`, and `_shell.py` removal are not done. See Task 2 open question.

## Task 1: pi and agy prompt input

Evidence, read in this session. No model run was started.

- `pi` (`@earendil-works/pi-coding-agent`, `pi --help`): `--print, -p` is non-interactive mode. `--mode` takes `text`, `json`, or `rpc`. Positional `[messages...]` and `[@files...]` are accepted.
- `pi` source, `dist/main.js` line 52 `readPipedStdin()`: returns `undefined` on a TTY, otherwise reads stdin to EOF. Line 727 calls it for every mode except `rpc`. Line 171 `prepareInitialMessage` passes `stdinContent` to `buildInitialMessage`.
- Decision for `pi`: stdin. Not verified end to end. The minified `buildInitialMessage` body was not fully read, so combining stdin with positional messages is unconfirmed.
- `agy` (`agy --help`): `--print` takes the prompt as its value (`--prompt` is an alias). There is no prompt-file option. `--input-format stream-json` reads one NDJSON message per line from stdin, but the message schema is not in the help text. A plain-text stdin mode is not documented in help.
- An earlier session cited an `agy` changelog entry for valueless `--print` reading stdin. It was not re-found in this session, so it is not used here.
- Decision for `agy`: unresolved. The temp-file option does not exist. Options are argv with a clear failure above 100 KiB, or `--input-format stream-json` after its schema is confirmed. Needs a coordinator decision.

## Task 2: async transport (`run_process`)

RED evidence. `server/tests/test_transport.py` was run with `server/src/refract/backends/_process.py` moved aside:

    ERROR tests/test_transport.py
    !!! Interrupted: 1 error during collection !!!
    1 error in 0.10s

GREEN evidence:

    12 passed in 3.84s   (test_transport.py, with -W error::pytest.PytestUnraisableExceptionWarning)

Full suite after the change: `1097 passed, 15 deselected in 48.20s` (1085 baseline plus 12 new).
Plugin: `test-session-start.sh`, `test-contracts.sh`, and `test-stats.sh` each exit 0.

Files:
- Added `server/src/refract/backends/_process.py`: `run_process`, `ProcessOutcome`, `_Tail`, `_discard_until_eof`.
- Added `server/tests/test_transport.py` (12 tests).
- Added `server/tests/fixtures/fake_cli/` (10 scripts).
- Modified `server/src/refract/processes.py`: added `kill_process_tree` (POSIX `killpg` SIGKILL, Windows `taskkill /F /T`). `terminate_process_tree` is kept because `_shell.py` still uses it.

Decisions:
- Newest output line is always kept in the tail even when it exceeds 64 KiB. The tail is therefore at most 64 KiB plus one line of at most 1 MiB. Needed so a single large non-streaming JSON result is not truncated.
- After the leader exits, the grace path waits up to 2 s for stdout EOF, then kills the group. After EOF with the leader still running, the loop keeps polling until the leader exits or the deadline or cancel fires.
- Stdin write failures are checked in the loop and again after the loop. They are reported as `stdin_failed` with `stdin write failed: <Type>: <message>`.
- Parser or callback exceptions are reported as `execution_error` with `<Type>: <message>`.
- The killed group's leftover output is drained in `finally`. Without this, stopped pipes stay open and asyncio warns when it garbage-collects the transport after the loop closes.

Open question (blocks Task 2 completion): the reviewer rule "no unbounded buffer of all lines or events" conflicts with the backends. All four backends read all retained lines and events after the run (`claude._extract_output` and `_final_result`, `pi._extract_output`, `agy.agent_messages` and `_CONVERSATION_ID_RE` over `stream.lines`, `codex` `stdout_text` and session ID extraction). A 64 KiB tail would drop early session IDs and non-JSON diagnostics. Options:
1. Replace post-run scans with incremental per-backend state updated in `on_line`. Larger change, touches all four parsers.
2. Keep bounded per-run diagnostics and session state in parser objects, with a documented cap.

Not done:
- `backends/claude.py`, `codex.py`, `pi.py`, `agy.py` still use `_shell.py`.
- `drivers.py` `StreamBridge` and `asyncio.to_thread` are still present.
- `execution.py` drain and bridge logic is unchanged.
- `_shell.py` is not deleted.
- The Phase 2 acceptance grep (`to_thread|StreamBridge|_shell|threading`) still matches.
- About 150 test patch sites (`run_shell_command`) are unchanged.
