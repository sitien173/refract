from __future__ import annotations

import asyncio
import dataclasses
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from refract.config import DaemonConfig, ProfileDeclaration, TargetConfig, TargetSelection
from refract.drivers import DriverResult
from refract.models import ProjectView


def git(path: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(path), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return completed.stdout.strip()


def register_project(runtime, path: str) -> ProjectView:
    resolved = Path(path).expanduser().resolve()
    return runtime.database.upsert_project(project_id=str(uuid.uuid4()), root=resolved.as_posix())


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Refract Tests")
    git(root, "config", "user.email", "refract@example.invalid")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "baseline")
    return root


def config(home: Path, targets: tuple[TargetConfig, ...] | None = None) -> DaemonConfig:
    resolved_targets = targets or (TargetConfig(id="primary", backend="codex"),)
    selection = TargetSelection(tuple(target.id for target in resolved_targets))
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


@dataclasses.dataclass(frozen=True)
class Raised:
    """Expected failure of a characterization case: exception type and exact message."""

    exc_type: type[Exception]
    message: str


def plain(value: object) -> object:
    """Order-preserving structural form: dicts keep key order, dataclasses keep field names."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (type(value).__name__, [(f.name, plain(getattr(value, f.name))) for f in dataclasses.fields(value)])
    if isinstance(value, dict):
        return ("dict", [(plain(key), plain(item)) for key, item in value.items()])
    if isinstance(value, (list, tuple)):
        return type(value)(plain(item) for item in value)
    return (type(value).__name__, value)


def outcome(call: Callable[[], object]) -> object:
    """Return the structural form of the result of `call`, or of the `Raised` it produced."""
    try:
        return plain(call())
    except Exception as exc:  # noqa: BLE001
        return plain(Raised(type(exc), str(exc)))


class FakeDrivers:
    def __init__(self, outcomes: dict[str, str] | None = None, mutate: bool = False) -> None:
        self.outcomes = outcomes or {}
        self.mutate = mutate
        self.sessions: list[str] = []

    @staticmethod
    async def supports_structured_streaming(target: TargetConfig, cancel_event=None) -> bool:
        return True

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
