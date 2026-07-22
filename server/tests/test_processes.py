from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from openmcp.backends._shell import ShellCommandCancelled, stream_shell_command_lines


def test_shell_command_rejects_cancelled_start(tmp_path) -> None:
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ShellCommandCancelled):
        list(stream_shell_command_lines([sys.executable, "-c", "import time; time.sleep(10)"], executable_name=Path(sys.executable).name, cwd=str(tmp_path), line_transform=lambda value: value, terminate_wait_s=1, cancel_event=cancelled))
