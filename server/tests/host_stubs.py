"""Stub host CLIs and the git environment shared by updater and installer tests."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from tests.launchers import install_launcher

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class Env:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.refract_home = root / "refract-home"
        self.claude_dir = root / "claude-config"
        self.pi_dir = root / "pi-agent"
        self.stubs = root / "stubs"
        self.calls = root / "calls.log"
        self.home.mkdir()
        self.stubs.mkdir()
        self.real_git = shutil.which("git") or "git"
        path = [str(self.stubs)]
        if sys.platform != "win32":
            gitbin = root / "gitbin"
            gitbin.mkdir()
            (gitbin / "git").symlink_to(self.real_git)
            path.append(str(gitbin))
        else:
            path.append(str(Path(self.real_git).parent))
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if powershell:
                path.append(str(Path(powershell).parent))
            # kill_process_tree resolves taskkill.exe through PATH; a real Windows PATH always has System32.
            path.append(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"))
        self.path = os.pathsep.join(path)

    def stub(self, name: str, stdout: str = "", code: int = 0, body: str | None = None) -> None:
        """Install a stub executable that logs its argv and prints stdout.

        ``body`` is Python source run after the call is logged, with ``sys``, ``args`` and ``joined`` in scope.
        """
        data = self.root / f"{name}.out"
        data.write_text(stdout)
        script = body or f"sys.stdout.write(open({str(data)!r}).read())\nsys.exit({code})"
        path = self.stubs / f"{name}_stub.py"
        path.write_text(
            "import sys\n"
            "args = sys.argv[1:]\n"
            'joined = " ".join(args)\n'
            f'with open({str(self.calls)!r}, "a", newline="\\n") as log:\n'
            f'    log.write(f"{name} {{joined}}\\n")\n'
            f"{script}\n"
        )
        install_launcher(self.stubs, name, path)

    def call_log(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []
