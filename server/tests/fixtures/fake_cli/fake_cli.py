"""Fake backend CLI for tests, used by the claude, pi, and agy stubs.

argv[1] is a JSON config file. argv[2:] are the arguments the backend passed.
The config keys are optional: ``name`` (executable name for the record), ``record``
(path to write argv, stdin, and cwd), ``pid_file`` (path to write this PID),
``raw_hex`` (stdout lines written verbatim from hex, before ``lines``), ``lines``
(stdout lines to print), ``log_text`` (written to the path after ``--log-file``), ``last_message`` (written to the path after ``-o``),
``sleep_s`` (seconds to sleep after printing), ``stderr_lines`` (stderr lines to print),
``ask_question`` (run ``refract ask`` with this question), ``ready_file`` (path to write
when ready), ``block_forever`` (sleep until terminated), and ``exit_code``.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
argv = sys.argv[2:]
prompt = sys.stdin.read()

if config.get("record"):
    Path(config["record"]).write_text(
        json.dumps({"argv": [config.get("name", "claude"), *argv], "stdin": prompt, "cwd": os.getcwd()}),
        encoding="utf-8",
    )
if config.get("pid_file"):
    Path(config["pid_file"]).write_text(str(os.getpid()), encoding="utf-8")
if config.get("log_text") is not None and "--log-file" in argv:
    Path(argv[argv.index("--log-file") + 1]).write_text(config["log_text"], encoding="utf-8")

if config.get("last_message") is not None and "-o" in argv:
    Path(argv[argv.index("-o") + 1]).write_text(config["last_message"], encoding="utf-8")

for hex_line in config.get("raw_hex", []):
    sys.stdout.buffer.write(bytes.fromhex(hex_line) + b"\n")
    sys.stdout.buffer.flush()

for line in config.get("lines", []):
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()

for err_line in config.get("stderr_lines", []):
    sys.stderr.buffer.write(err_line.encode("utf-8") + b"\n")
    sys.stderr.buffer.flush()

if config.get("ready_file"):
    Path(config["ready_file"]).write_text("ready\n", encoding="utf-8")

if config.get("ask_question"):
    answer = subprocess.run(
        ["refract", "ask", str(config["ask_question"])],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    ).stdout.strip()
    sys.stdout.buffer.write(answer.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()

if config.get("block_forever"):
    while True:
        time.sleep(0.2)

if config.get("sleep_s"):
    time.sleep(config["sleep_s"])

sys.exit(config.get("exit_code", 0))
