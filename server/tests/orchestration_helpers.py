from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from openmcp.config import DaemonConfig, ProfileDeclaration, TargetConfig, TargetSelection
from openmcp.drivers import DriverResult


def git(path: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(path), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return completed.stdout.strip()


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "OpenMCP Tests")
    git(root, "config", "user.email", "openmcp@example.invalid")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "baseline")
    return root


def config(home: Path, targets: tuple[TargetConfig, ...] | None = None) -> DaemonConfig:
    resolved_targets = targets or (TargetConfig(id="primary", backend="codex"),)
    selection = TargetSelection(tuple(target.id for target in resolved_targets), len(resolved_targets))
    return DaemonConfig(
        home=home,
        max_jobs=2,
        default_profile="balanced",
        targets=resolved_targets,
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection, "other": selection}},
        profile_declarations={
            "balanced": ProfileDeclaration(
                workflows={
                    "implement": selection,
                    "review": selection,
                    "consult": selection,
                    "other": selection,
                }
            )
        },
    )


class FakeDrivers:
    def __init__(self, outcomes: dict[str, str] | None = None, mutate: bool = False) -> None:
        self.outcomes = outcomes or {}
        self.mutate = mutate
        self.sessions: list[str] = []

    @staticmethod
    def available(target: TargetConfig) -> bool:
        return True

    async def execute(self, *, target: TargetConfig, cwd: Path, session_id: str, **kwargs) -> DriverResult:
        self.sessions.append(session_id)
        outcome = self.outcomes.get(target.id, "SUCCESS")
        if outcome == "SUCCESS" and self.mutate:
            (cwd / "result.txt").write_text(f"created by {target.id}\n", encoding="utf-8")
        return DriverResult(outcome=outcome, session_id=session_id or f"session-{target.id}", text=f"response from {target.id}" if outcome == "SUCCESS" else "", error="" if outcome == "SUCCESS" else f"{target.id} failed", error_code="" if outcome == "SUCCESS" else "backend_failure")


class BlockingDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def execute(self, *, cancel_event, **kwargs) -> DriverResult:
        self.started.set()
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        return DriverResult("CANCELLED", "", "", "cancelled", "cancelled")


class ExplodingDrivers(FakeDrivers):
    async def execute(self, **kwargs) -> DriverResult:
        raise RuntimeError("driver exploded")


class ChangingDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, *, cwd: Path, session_id: str, target: TargetConfig, **kwargs) -> DriverResult:
        self.calls += 1
        (cwd / f"result-{self.calls}.txt").write_text("created\n", encoding="utf-8")
        return DriverResult("SUCCESS", session_id or f"session-{target.id}", f"response {self.calls}", "", "")
