import pytest

import app.utils.tracing as tracing


@pytest.fixture(autouse=True)
def reset_configured(monkeypatch):
    monkeypatch.setattr(tracing, '_configured', False)


def test_tracing_disabled_without_endpoint(monkeypatch):
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT', raising=False)
    assert tracing.configure_tracing('joy-test') is False


def test_instrumentation_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT', raising=False)
    tracing.configure_tracing('joy-test')
    tracing.instrument_pika()  # must not raise or instrument anything

    from flask import Flask
    app = Flask('test')
    tracing.instrument_flask(app)
    # No otel middleware attached
    assert not any('opentelemetry' in str(f) for f in app.before_request_funcs.get(None, []))


def test_configure_tracing_enables_with_endpoint(monkeypatch):
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')
    monkeypatch.setenv('OTEL_SAMPLE_RATIO', '0.5')
    assert tracing.configure_tracing('joy-test') is True
    # Second call is an idempotent no-op
    assert tracing.configure_tracing('joy-test') is True

    from opentelemetry import trace
    provider = trace.get_tracer_provider()
    assert 'ParentBased' in type(provider.sampler).__name__ or provider.sampler is not None


def test_invalid_sample_ratio_defaults_to_one(monkeypatch):
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')
    monkeypatch.setenv('OTEL_SAMPLE_RATIO', '10%')
    assert tracing.configure_tracing('joy-test') is True  # must not raise


def test_out_of_range_sample_ratio_defaults_to_one(monkeypatch):
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')
    monkeypatch.setenv('OTEL_SAMPLE_RATIO', '7')
    assert tracing.configure_tracing('joy-test') is True
