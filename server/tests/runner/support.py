"""Scripted drivers and a runtime builder shared by the attempt loop tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from refract.config import RetryPolicy, TargetConfig, TargetSelection
from refract.runner.drivers import DriverResult
from refract.runner.planning import target_execution_key
from refract.runtime import Runtime
from tests.orchestration_helpers import FakeDrivers, config, register_project, repository

TRANSIENT = DriverResult("RETRYABLE", "", "", "temporary", "rate_limit")
OVERFLOW = DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow")
FATAL = DriverResult("TARGET_FATAL", "", "", "target is broken", "backend_failure")
OK = DriverResult("SUCCESS", "sid", "done", "", "")


@dataclass(slots=True)
class Step:
    result: DriverResult
    tool: bool = False
    ask: bool = False


class ScriptedDrivers(FakeDrivers):
    """Each call pops the next `Step`; calls past the script succeed."""

    def __init__(self, *steps: DriverResult | Step, probe_fails: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.probe_fails = probe_fails
        self.steps = [step if isinstance(step, Step) else Step(step) for step in steps]
        self.calls: list[tuple[str, str]] = []
        self.database = None
        self.runtime: Runtime | None = None

    async def supports_structured_streaming(self, target, cancel_event=None) -> bool:
        return target.id not in self.probe_fails

    async def execute(self, *, target, session_id, on_event=None, env=None, **kwargs) -> DriverResult:
        self.calls.append((target.id, session_id))
        step = self.steps.pop(0) if self.steps else Step(OK)
        if step.tool and on_event:
            await on_event({"kind": "tool.started", "tool_name": "bash"})
        if step.ask:
            question_id = self.database.ask_question((env or {})["REFRACT_JOB_ID"], "Proceed?")
            self.database.answer_question(question_id, "yes")
        return step.result


async def run_job(
    tmp_path: Path, drivers: ScriptedDrivers, targets: tuple[TargetConfig, ...], *,
    fresh: bool = False, prepare=None, session: str = "",
):
    """Run one job over `targets` in order; return (runtime, job, attempt rows). The caller closes nothing."""
    selection = TargetSelection(tuple(target.id for target in targets))
    catalog = replace(
        config(tmp_path / "home"), targets=targets,
        profiles={"balanced": {name: selection for name in ("implement", "review", "consult", "other")}},
    )
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    drivers.database = runtime.database
    drivers.runtime = runtime
    await runtime.start()
    project = register_project(runtime, str(repository(tmp_path)))
    if prepare:
        prepare(runtime, project)
    sub = await runtime.submit(project.id, "implement", "prompt", fresh=fresh, **({"session": session} if session else {}))
    job = await runtime.wait(sub.job_id, 10)
    rows = [tuple(row) for row in runtime.database._connection.execute(
        "SELECT reason, target, state, failure_kind, replay_safe FROM attempts WHERE job_id=? ORDER BY seq", (job.id,))]
    return runtime, job, rows


def target(target_id: str, *, backend: str = "claude", retry: RetryPolicy | None = None) -> TargetConfig:
    return TargetConfig(id=target_id, backend=backend, retry=retry or RetryPolicy(0, (), ()))


def open_circuit(runtime: Runtime, tgt: TargetConfig) -> None:
    with runtime.database._connection:
        runtime.database._connection.execute(
            "INSERT INTO target_health(target_id, circuit_open_until, cooldown_s) VALUES (?, '2999-01-01T00:00:00+00:00', 60)",
            (target_execution_key(tgt),),
        )
