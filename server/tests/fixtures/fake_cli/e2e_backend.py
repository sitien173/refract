from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

if "--help" in sys.argv:
    print("--output-format stream-json --include-partial-messages")
    raise SystemExit(0)

prompt = sys.stdin.read()


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event), flush=True)


if "E2E_MODE=block" in prompt:
    emit({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Waiting for cancellation"}})
    while True:
        time.sleep(1)

if "E2E_MODE=ask" in prompt:
    match = re.search(r"E2E_ASK:\s*(.+)", prompt)
    question = match.group(1).strip() if match else "Should the e2e test continue?"
    answer = subprocess.run(
        ["refract", "ask", question],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    ).stdout.strip()
    output = answer
else:
    output = "E2E backend completed"

emit({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": output}})
emit({"type": "result", "subtype": "success", "result": output, "session_id": "e2e-session"})
