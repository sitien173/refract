"""Langfuse observability client wrapper and lifecycle management."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from refract.config import LangfuseConfig
from refract.logging_setup import get_logger

log = get_logger("observability")


def _get_refract_version() -> str:
    try:
        from importlib.metadata import version

        return version("refract")
    except Exception:
        return "2.0.0"


def trace_id_for_job(job_id: str) -> str:
    """Generate deterministic 32-character lowercase hex trace ID for a job ID."""
    try:
        if not isinstance(job_id, str):
            raise TypeError("job_id must be a string")
        raw = ("refract:job:" + job_id).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32].lower()
    except Exception as exc:
        log.warning(
            f"Failed to generate trace ID for job: {exc}",
            extra={"event": "langfuse.error"},
        )
        return ""


class Tracer:
    """Langfuse observability client wrapper and lifecycle holder."""

    def __init__(
        self,
        config: LangfuseConfig | None = None,
        *,
        span_exporter: Any = None,
    ) -> None:
        self._config = config or LangfuseConfig()
        self._client: Any = None
        self._tracer_provider: Any = None
        self._is_active: bool = False
        self._public_key: str = ""

        if not self._config.enabled:
            return

        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
        if not public_key or not secret_key:
            log.warning(
                "Langfuse enabled but LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is missing",
                extra={"event": "langfuse.error"},
            )
            return

        if os.environ.get("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
            log.warning(
                "Langfuse tracing is disabled by LANGFUSE_TRACING_ENABLED",
                extra={"event": "langfuse.error"},
            )
            return

        self._public_key = public_key

        try:
            from langfuse import Langfuse
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        except ImportError as exc:
            log.warning(
                f"Langfuse enabled but import failed: {exc}",
                extra={"event": "langfuse.error"},
            )
            return
        except Exception as exc:
            log.warning(
                f"Failed to load Langfuse dependencies: {exc}",
                extra={"event": "langfuse.error"},
            )
            return

        try:
            release = _get_refract_version()
            self._tracer_provider = TracerProvider(
                sampler=TraceIdRatioBased(self._config.sample_rate),
                resource=Resource.create({
                    "langfuse.environment": self._config.environment,
                    "langfuse.release": release,
                }),
            )
            kwargs: dict[str, Any] = {
                "public_key": public_key,
                "secret_key": secret_key,
                "base_url": self._config.base_url,
                "environment": self._config.environment or None,
                "sample_rate": self._config.sample_rate,
                "release": release,
                "tracer_provider": self._tracer_provider,
            }
            if span_exporter is not None:
                kwargs["span_exporter"] = span_exporter

            client = Langfuse(**kwargs)
            # SDK v4 caches resources by key. Never borrow another host's provider.
            if client._resources.tracer_provider is not self._tracer_provider:
                raise RuntimeError("Langfuse key is already managed by another client")
            self._client = client
            self._is_active = True
        except Exception as exc:
            log.warning(
                f"Failed to initialize Langfuse client: {exc}",
                extra={"event": "langfuse.error"},
            )
            if self._tracer_provider is not None:
                try:
                    self._tracer_provider.shutdown()
                except Exception:
                    # The initialization failure was already reported once.
                    pass
            self._client = None
            self._tracer_provider = None
            self._is_active = False

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def client(self) -> Any:
        return self._client

    @property
    def config(self) -> LangfuseConfig:
        return self._config

    def flush(self) -> None:
        try:
            if self._client is not None:
                self._client.flush()
        except Exception as exc:
            log.warning(
                f"Langfuse flush error: {exc}",
                extra={"event": "langfuse.error"},
            )

    def shutdown(self) -> None:
        error = None
        for resource in (self._client, self._tracer_provider):
            if resource is not None:
                try:
                    resource.shutdown()
                except Exception as exc:
                    error = error or exc
        try:
            if self._client is not None:
                from langfuse._client.resource_manager import LangfuseResourceManager

                # v4 shutdown leaves a stopped singleton cached. Remove only ours,
                # never reset the registry or another client's resources.
                with LangfuseResourceManager._lock:
                    if LangfuseResourceManager._instances.get(self._public_key) is self._client._resources:
                        del LangfuseResourceManager._instances[self._public_key]
        except Exception as exc:
            error = error or exc
        self._client = None
        self._tracer_provider = None
        self._is_active = False
        if error is not None:
            log.warning(
                "Langfuse shutdown error: %s", error,
                extra={"event": "langfuse.error"},
            )


@dataclass
class _Observation:
    handle: Any = None

    def finish(self, *, output: Any = None, metadata: dict[str, Any] | None = None,
               level: str | None = None, status_message: str | None = None,
               accumulator: Any = None, attempt: int | None = None,
               model: str | None = None) -> None:
        try:
            if self.handle is not None:
                kwargs: dict[str, Any] = {
                    "output": output, "metadata": metadata,
                    "level": level, "status_message": status_message,
                }
                if accumulator is not None:
                    totals = accumulator._calculate_attempt_totals(attempt)
                    if not accumulator._responses and not accumulator._cumulative_invocations:
                        loaded = (accumulator._loaded_total_input, accumulator._loaded_total_output,
                                  accumulator._loaded_cache_read, accumulator._loaded_cache_write)
                        completed = accumulator._completed_attempts
                        prior = (completed.total_input_tokens, completed.total_output_tokens,
                                 completed.cache_read_tokens, completed.cache_write_tokens)
                        totals = tuple(
                            max(0, value - previous) if value is not None else None
                            for value, previous in zip(loaded, prior, strict=True)
                        )
                    usage = {key: value for key, value in zip(
                        ("input", "output", "input_cached_tokens", "cache_creation_input_tokens"),
                        totals, strict=True,
                    ) if value is not None}
                    if "input" in usage:
                        # Canonical input includes caches; SDK categories are exclusive.
                        usage["input"] = max(0, usage["input"] - usage.get("input_cached_tokens", 0)
                                             - usage.get("cache_creation_input_tokens", 0))
                    kwargs.update(usage_details=usage or None, model=model)
                self.handle.update(**kwargs)
        except Exception as exc:
            log.warning("Langfuse observation update failed: %s", exc,
                        extra={"event": "langfuse.error"})


def record_tool_observation(
    tracer: Tracer | None, *, name: str, input: Any, output: Any,
    metadata: dict[str, Any], start_time_ns: int, end_time_ns: int,
    job_id: str | None, session_id: str | None,
) -> None:
    """Export a completed tool span with retrospective request timestamps."""
    try:
        if tracer is None or not tracer.is_active:
            return
        from langfuse import propagate_attributes
        from opentelemetry import trace as otel_trace
        parent = None
        if job_id:
            parent = tracer.client._create_remote_parent_span(
                trace_id=trace_id_for_job(job_id), parent_span_id=None
            )
        scope = otel_trace.use_span(parent) if parent is not None else propagate_attributes(
            session_id=session_id
        )
        otel_span = None
        try:
            with scope:
                otel_span = tracer.client._otel_tracer.start_span(name=name, start_time=start_time_ns)
                observation = tracer.client._create_observation_from_otel_span(
                    otel_span=otel_span, as_type="tool", input=input, output=output,
                    metadata=metadata,
                )
                observation.end(end_time=end_time_ns)
        finally:
            if otel_span is not None and otel_span.is_recording():
                otel_span.end(end_time=end_time_ns)
    except Exception as exc:
        _warn_helper("tool observation", exc)


def _warn_helper(name: str, exc: Exception) -> None:
    log.warning("Langfuse %s failed: %s", name, exc,
                extra={"event": "langfuse.error"})


@contextmanager
def job_observation(tracer: Tracer, job_id: str, session_id: str, prompt: str) -> Iterator[_Observation]:
    """Open the job agent on its deterministic trace; failures are non-fatal."""
    observation = _Observation()
    manager = propagation = None
    try:
        if tracer.is_active:
            from langfuse import propagate_attributes
            propagation_candidate = propagate_attributes(session_id=session_id)
            propagation_candidate.__enter__()
            propagation = propagation_candidate
            manager_candidate = tracer.client.start_as_current_observation(
                name="job", as_type="agent", input=prompt,
                trace_context={"trace_id": trace_id_for_job(job_id)},
            )
            observation.handle = manager_candidate.__enter__()
            manager = manager_candidate
    except Exception as exc:
        _warn_helper("job observation", exc)
    try:
        yield observation
    finally:
        for active in (manager, propagation):
            if active is not None:
                try:
                    active.__exit__(None, None, None)
                except Exception as exc:
                    _warn_helper("job observation finish", exc)


@contextmanager
def generation_observation(
    tracer: Tracer, *, name: str, model: str, input_text: str,
    metadata: dict[str, Any], usage: dict[str, int] | None,
) -> Iterator[_Observation]:
    observation = _Observation()
    manager = None
    try:
        if tracer.is_active:
            kwargs: dict[str, Any] = {
                "name": name, "as_type": "generation", "model": model,
                "input": input_text, "metadata": metadata,
            }
            if usage:
                kwargs["usage_details"] = usage
            manager_candidate = tracer.client.start_as_current_observation(**kwargs)
            observation.handle = manager_candidate.__enter__()
            manager = manager_candidate
    except Exception as exc:
        _warn_helper("generation observation", exc)
    try:
        yield observation
    finally:
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:
                _warn_helper("generation observation finish", exc)


def job_event(tracer: Tracer, job_id: str, name: str, text: str) -> None:
    try:
        if tracer.is_active:
            tracer.client.create_event(
                trace_context={"trace_id": trace_id_for_job(job_id)},
                name=name, input=text,
            )
    except Exception as exc:
        _warn_helper("job event", exc)


__all__ = [
    "Tracer",
    "trace_id_for_job",
    "job_observation",
    "generation_observation",
    "job_event",
    "record_tool_observation",
]
