from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

from refract.config import LangfuseConfig
from refract.observability import Tracer, trace_id_for_job
import refract.observability as observability


def test_job_generation_and_events_export_on_one_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-phase2-integration")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-phase2-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True), span_exporter=exporter)
    assert tracer.is_active
    job_id = "phase2-integration"
    try:
        with observability.job_observation(tracer, job_id, "project:context", "prompt") as job:
            with observability.generation_observation(
                tracer, name="target-attempt", model="model-x", input_text="effective prompt",
                metadata={"target_id": "target-x", "backend": "backend-x", "attempt": 1},
                usage={"input": 12, "input_cached_tokens": 3},
            ) as generation:
                generation.finish(output="answer")
            with observability.generation_observation(
                tracer, name="retry-attempt", model="model-x", input_text="effective prompt",
                metadata={"target_id": "target-x", "backend": "backend-x", "attempt": 2},
                usage={"input": 4},
            ) as retry:
                retry.finish(output="retried answer")
            job.finish(output="answer", metadata={"workflow": "implement", "profile": "balanced", "final_state": "succeeded"})
            observability.job_event(tracer, job_id, "question", "Question text")
            observability.job_event(tracer, job_id, "answer", "Answer text")
        with tracer.client.start_as_current_observation(name="unrelated"):
            pass
        tracer.flush()
        spans = exporter.get_finished_spans()
        assert spans
        by_name = {span.name: span for span in spans}
        assert "session.id" not in by_name["unrelated"].attributes
        root = by_name["job"]
        child = by_name["target-attempt"]
        retry_child = by_name["retry-attempt"]
        assert root.context.trace_id == int(trace_id_for_job(job_id), 16)
        assert child.parent.span_id == root.context.span_id
        assert retry_child.parent.span_id == root.context.span_id
        assert '"input": 4' in retry_child.attributes["langfuse.observation.usage_details"]
        assert child.attributes["langfuse.observation.model.name"] == "model-x"
        assert child.attributes["langfuse.observation.input"] == "effective prompt"
        assert child.attributes["langfuse.observation.output"] == "answer"
        assert '"input": 12' in child.attributes["langfuse.observation.usage_details"]
        assert root.attributes["langfuse.observation.input"] == "prompt"
        assert root.attributes["langfuse.observation.output"] == "answer"
        assert root.attributes["session.id"] == "project:context"
        events = {span.name: span for span in spans if span.name in {"question", "answer"}}
        assert events["question"].attributes["langfuse.observation.input"] == "Question text"
        assert events["answer"].attributes["langfuse.observation.input"] == "Answer text"
        assert sum(span.name in {"question", "answer"} for span in spans) == 2
    finally:
        tracer.shutdown()


@pytest.mark.asyncio
async def test_ask_registry_emits_only_published_questions_and_delivered_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from refract.ask import AskRegistry

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-phase2-ask")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-phase2-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True), span_exporter=exporter)
    registry = AskRegistry(tracer)
    token = registry.issue_token("ask-job")
    question = asyncio.create_task(registry.ask(token, "What next?", 2, "ask-job"))
    try:
        pending = await registry.wait_question("ask-job", 1)
        assert pending is not None
        assert registry.deliver_answer("ask-job", "Continue") is True
        assert await question == "Continue"
        assert registry.deliver_answer("ask-job", "ignored") is False
        tracer.flush()
        events = {span.name: span for span in exporter.get_finished_spans()}
        assert set(events) == {"question", "answer"}
        assert events["question"].attributes["langfuse.observation.input"] == "What next?"
        assert events["answer"].attributes["langfuse.observation.input"] == "Continue"
        assert events["question"].context.trace_id == events["answer"].context.trace_id
        assert events["question"].context.trace_id == int(trace_id_for_job("ask-job"), 16)
    finally:
        if not question.done():
            question.cancel()
        tracer.shutdown()


@pytest.mark.parametrize(
    ("field", "key", "value", "completed_field", "completed_value", "expected"),
    [
        ("total_output_tokens", "output", 37, "total_output_tokens", 12, 25),
        ("cache_read_tokens", "input_cached_tokens", 9, "cache_read_tokens", 3, 6),
    ],
)
def test_loaded_measurement_exports_when_input_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, field: str, key: str, value: int,
    completed_field: str, completed_value: int, expected: int,
) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from refract.telemetry import TelemetryAccumulator

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", f"pk-loaded-{key}")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-phase2-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True), span_exporter=exporter)
    accumulator = TelemetryAccumulator({
        field: {"value": value, "source": "provider", "quality": "reported"},
        "completed_attempts": {completed_field: completed_value},
    })
    try:
        with observability.generation_observation(
            tracer, name=f"loaded-{key}", model="model-x", input_text="prompt",
            metadata={}, usage=None,
        ) as generation:
            generation.finish(output="result", accumulator=accumulator, attempt=1, model="model-x")
        tracer.flush()
        span = exporter.get_finished_spans()[0]
        details = json.loads(span.attributes["langfuse.observation.usage_details"])
        assert details == {key: expected}
    finally:
        tracer.shutdown()


def test_cancelled_job_observation_exports_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-phase2-cancel")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-phase2-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True), span_exporter=exporter)
    try:
        with observability.job_observation(tracer, "cancel-job", "p:c", "prompt") as job:
            job.finish(level="WARNING", status_message="cancelled", metadata={"final_state": "cancelled"})
        tracer.flush()
        root = exporter.get_finished_spans()[0]
        assert root.attributes["langfuse.observation.level"] == "WARNING"
        assert root.attributes["langfuse.observation.status_message"] == "cancelled"
    finally:
        tracer.shutdown()


def test_tool_observation_uses_retrospective_timestamps_and_job_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-phase3-tool")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-phase3-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True), span_exporter=exporter)
    start_ns = 1_800_000_000_000_000_000
    end_ns = start_ns + 25_000_000
    try:
        observability.record_tool_observation(
            tracer, name="job_submit", input={"project_id": "project-x"}, output='{"job":{"id":"phase3-job"}}',
            metadata={"outcome": "success", "error_type": "", "duration_ms": 10.0},
            start_time_ns=start_ns, end_time_ns=start_ns + 10_000_000,
            job_id="phase3-job", session_id="project-x",
        )
        observability.record_tool_observation(
            tracer, name="job_wait", input={"job_id": "phase3-job"}, output="result",
            metadata={"outcome": "success", "error_type": "", "duration_ms": 25.0},
            start_time_ns=start_ns, end_time_ns=end_ns,
            job_id="phase3-job", session_id=None,
        )
        tracer.flush()
        spans = {span.name: span for span in exporter.get_finished_spans()}
        assert set(spans) == {"job_submit", "job_wait"}
        for span in spans.values():
            assert span.context.trace_id == int(trace_id_for_job("phase3-job"), 16)
            assert span.attributes["langfuse.observation.type"] == "tool"
        span = spans["job_wait"]
        assert span.start_time == start_ns
        assert span.end_time == end_ns
        assert span.attributes["langfuse.observation.input"] == '{"job_id": "phase3-job"}'
        assert span.attributes["langfuse.observation.output"] == "result"
    finally:
        tracer.shutdown()


def test_tool_observation_conversion_failure_closes_raw_span(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("langfuse")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-phase3-conversion-failure")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-phase3-test")
    exporter = InMemorySpanExporter()
    tracer = Tracer(LangfuseConfig(enabled=True), span_exporter=exporter)
    original_start = tracer.client._otel_tracer.start_span
    retained = []

    def capture_span(*args, **kwargs):
        span = original_start(*args, **kwargs)
        retained.append(span)
        return span

    monkeypatch.setattr(tracer.client._otel_tracer, "start_span", capture_span)
    monkeypatch.setattr(tracer.client, "_create_observation_from_otel_span", lambda **_: (_ for _ in ()).throw(RuntimeError("conversion failed")))
    try:
        observability.record_tool_observation(
            tracer, name="job_wait", input={}, output="same-result", metadata={},
            start_time_ns=1_800_000_000_000_000_000,
            end_time_ns=1_800_000_001_000_000_000,
            job_id="failed-tool", session_id=None,
        )
        assert retained
        assert retained[0].is_recording() is False
        tracer.flush()
        assert len(exporter.get_finished_spans()) == 1
    finally:
        tracer.shutdown()


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


def test_sdk_environment_disablement_does_not_poison_same_key_recovery(monkeypatch) -> None:
    pytest.importorskip("langfuse")
    from langfuse._client.resource_manager import LangfuseResourceManager
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    key = "pk-disabled-recovery"
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", key)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    disabled = Tracer(LangfuseConfig(enabled=True), span_exporter=InMemorySpanExporter())
    try:
        assert disabled.is_active is False
        assert key not in LangfuseResourceManager._instances
        monkeypatch.delenv("LANGFUSE_TRACING_ENABLED")
        recovered = Tracer(LangfuseConfig(enabled=True), span_exporter=InMemorySpanExporter())
        try:
            assert recovered.is_active is True
        finally:
            recovered.shutdown()
    finally:
        disabled.shutdown()
        # Clean up the pre-fix SDK leak so the RED run remains isolated.
        resource = LangfuseResourceManager._instances.pop(key, None)
        if resource is not None:
            resource.shutdown()


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
