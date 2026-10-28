from __future__ import annotations

import logging
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

from refract.config import LangfuseConfig
from refract.observability import Tracer, trace_id_for_job


def test_trace_id_for_job_deterministic() -> None:
    job_id = "test-job-1234"
    id1 = trace_id_for_job(job_id)
    id2 = trace_id_for_job(job_id)

    assert len(id1) == 32
    assert id1 == id2
    assert id1 == id1.lower()
    assert all(c in "0123456789abcdef" for c in id1)

    id3 = trace_id_for_job("another-job-5678")
    assert id3 != id1
    assert len(id3) == 32


def test_trace_id_for_job_exception_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    # Pass an object that causes an exception
    result = trace_id_for_job(12345)  # type: ignore[arg-type]
    assert result == ""
    errors = [
        r for r in caplog.records
        if getattr(r, "event", None) == "langfuse.error" and r.levelname == "WARNING"
    ]
    assert len(errors) == 1


def test_tracer_disabled_by_default(caplog: pytest.LogCaptureFixture) -> None:
    config = LangfuseConfig(enabled=False)
    tracer = Tracer(config)

    assert tracer.is_active is False
    assert tracer.client is None

    # flush and shutdown should be no-ops
    tracer.flush()
    tracer.shutdown()

    # No warnings logged
    assert len(caplog.records) == 0


def test_tracer_enabled_missing_keys_logs_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    config = LangfuseConfig(enabled=True)
    tracer = Tracer(config)

    assert tracer.is_active is False
    assert tracer.client is None

    tracer.flush()
    tracer.shutdown()

    errors = [
        r for r in caplog.records
        if getattr(r, "event", None) == "langfuse.error" and r.levelname == "WARNING"
    ]
    assert len(errors) == 1
    assert "missing" in errors[0].message.lower() or "key" in errors[0].message.lower()


def test_tracer_enabled_import_error_logs_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setitem(sys.modules, "langfuse", None)

    config = LangfuseConfig(enabled=True)
    tracer = Tracer(config)

    assert tracer.is_active is False
    assert tracer.client is None

    errors = [
        r for r in caplog.records
        if getattr(r, "event", None) == "langfuse.error" and r.levelname == "WARNING"
    ]
    assert len(errors) == 1


def test_tracer_constructor_exception_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    mock_otel_sdk = MagicMock()
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk", mock_otel_sdk)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", mock_otel_sdk.trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", mock_otel_sdk.resources)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.sampling", mock_otel_sdk.trace.sampling)

    mock_langfuse_mod = MagicMock()
    mock_langfuse_mod.Langfuse.side_effect = RuntimeError("SDK initialization exploded")
    mock_otel_sdk.trace.TracerProvider.return_value.shutdown.side_effect = RuntimeError("cleanup failed")
    monkeypatch.setitem(sys.modules, "langfuse", mock_langfuse_mod)

    config = LangfuseConfig(enabled=True)
    tracer = Tracer(config)

    assert tracer.is_active is False
    assert tracer.client is None

    errors = [
        r for r in caplog.records
        if getattr(r, "event", None) == "langfuse.error" and r.levelname == "WARNING"
    ]
    assert len(errors) == 1
    assert "exploded" in errors[0].message or "initialization" in errors[0].message.lower()


def test_tracer_flush_and_shutdown_exceptions_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    mock_otel_sdk = MagicMock()
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk", mock_otel_sdk)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", mock_otel_sdk.trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", mock_otel_sdk.resources)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.sampling", mock_otel_sdk.trace.sampling)

    mock_client = MagicMock()
    mock_client.flush.side_effect = RuntimeError("flush failed")
    mock_client.shutdown.side_effect = RuntimeError("shutdown failed")

    mock_langfuse_mod = MagicMock()
    mock_langfuse_mod.Langfuse.return_value = mock_client
    mock_client._resources.tracer_provider = mock_otel_sdk.trace.TracerProvider.return_value
    monkeypatch.setitem(sys.modules, "langfuse", mock_langfuse_mod)

    config = LangfuseConfig(enabled=True)
    tracer = Tracer(config)

    assert tracer.is_active is True

    caplog.clear()
    tracer.flush()
    errors = [
        r for r in caplog.records
        if getattr(r, "event", None) == "langfuse.error" and r.levelname == "WARNING"
    ]
    assert len(errors) == 1
    assert "flush" in errors[0].message.lower()

    caplog.clear()
    tracer.shutdown()
    errors = [
        r for r in caplog.records
        if getattr(r, "event", None) == "langfuse.error" and r.levelname == "WARNING"
    ]
    assert len(errors) == 1
    assert "shutdown" in errors[0].message.lower()
    mock_otel_sdk.trace.TracerProvider.return_value.shutdown.assert_called_once()
    assert tracer.is_active is False
    assert tracer.client is None


def test_tracer_active_with_real_sdk_if_installed(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        import langfuse
    except ImportError:
        pytest.skip("langfuse extra not installed")

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    exporter = InMemorySpanExporter()
    config = LangfuseConfig(
        enabled=True,
        base_url="http://localhost:3000",
        environment="test",
        sample_rate=1.0,
    )
    tracer = Tracer(config, span_exporter=exporter)

    assert tracer.is_active is True
    assert tracer.client is not None

    # Global tracer provider is not replaced
    from opentelemetry import trace
    curr = trace.get_tracer_provider()
    assert type(curr).__name__ != "TracerProvider" or curr is not tracer._tracer_provider

    tracer.flush()
    tracer.shutdown()
    assert tracer.is_active is False


def test_tracer_same_public_key_lifecycle_and_rebuild(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        import langfuse
    except ImportError:
        pytest.skip("langfuse extra not installed")

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    exporter1 = InMemorySpanExporter()
    config1 = LangfuseConfig(
        enabled=True,
        base_url="http://localhost:3000",
        environment="test-env-1",
        sample_rate=1.0,
    )
    tracer1 = Tracer(config1, span_exporter=exporter1)
    assert tracer1.is_active is True
    with tracer1.client.start_as_current_observation(name="obs-1") as span:
        span.update(output="result-1")
    tracer1.flush()
    spans1 = exporter1.get_finished_spans()
    assert len(spans1) == 1
    tracer1.shutdown()
    assert tracer1.is_active is False

    # Second tracer with SAME public key but changed environment and new exporter
    exporter2 = InMemorySpanExporter()
    config2 = LangfuseConfig(
        enabled=True,
        base_url="http://localhost:3000",
        environment="test-env-2",
        sample_rate=1.0,
    )
    tracer2 = Tracer(config2, span_exporter=exporter2)
    assert tracer2.is_active is True
    with tracer2.client.start_as_current_observation(name="obs-2") as span:
        span.update(output="result-2")
    tracer2.flush()
    spans2 = exporter2.get_finished_spans()
    assert len(spans2) == 1
    assert spans2[0].attributes.get("langfuse.environment") == "test-env-2"
    tracer2.shutdown()
    assert tracer2.is_active is False


def test_zero_sampling_with_private_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-sampling-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-sampling-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True, sample_rate=0), span_exporter=exporter)
    try:
        with tracer.client.start_as_current_observation(name="not-sampled"):
            pass
        tracer.flush()
        assert exporter.get_finished_spans() == ()
    finally:
        tracer.shutdown()


def test_tracer_constructor_parameters_forwarded(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        import langfuse
    except ImportError:
        pytest.skip("langfuse extra not installed")

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-custom-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-custom-key")

    exporter = InMemorySpanExporter()
    config = LangfuseConfig(
        enabled=True,
        base_url="http://localhost:3000",
        environment="production-prod",
        sample_rate=0.75,
    )
    tracer = Tracer(config, span_exporter=exporter)
    try:
        assert tracer.is_active is True
        client = tracer.client
        assert client is not None
        assert client._base_url == "http://localhost:3000"
        assert getattr(client._resources, "environment", None) == "production-prod"
        assert getattr(client._resources, "sample_rate", None) == 0.75
        assert getattr(client._resources, "release", None) == "2.0.0"
    finally:
        tracer.shutdown()


