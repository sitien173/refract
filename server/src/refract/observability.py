"""Langfuse observability client wrapper and lifecycle management."""

from __future__ import annotations

import hashlib
import os
from typing import Any

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


__all__ = [
    "Tracer",
    "trace_id_for_job",
]
