"""OpenTelemetry setup shared by the API and the workers.

Tracing activates only when OTEL_EXPORTER_OTLP_ENDPOINT is set (the compose
file points it at Jaeger's OTLP receiver); without it everything stays a
no-op so tests and Redis-less local runs pay nothing.

Trace context propagates across the event bus via pika instrumentation:
the publisher injects traceparent headers into message properties and the
consumers continue the same trace.
"""
import logging
import os

logger = logging.getLogger(__name__)

_configured = False


def configure_tracing(service_name: str) -> bool:
    """Idempotent. Returns True when tracing was actually enabled."""
    global _configured
    endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
    if not endpoint or _configured:
        return _configured

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    try:
        ratio = float(os.getenv('OTEL_SAMPLE_RATIO', '1.0'))
        if not 0.0 <= ratio <= 1.0:
            raise ValueError
    except ValueError:
        # Tracing is optional; a bad ratio must not crash the service
        logger.warning('invalid OTEL_SAMPLE_RATIO %r, defaulting to 1.0',
                       os.getenv('OTEL_SAMPLE_RATIO'))
        ratio = 1.0
    provider = TracerProvider(
        resource=Resource.create({'service.name': service_name}),
        sampler=ParentBased(TraceIdRatioBased(ratio)),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    # atexit (which flushes buffered spans) doesn't run on SIGTERM — the
    # signal docker sends on stop/restart. Translate it so shutdown flushes.
    import signal
    import sys

    def _terminate(signum, frame):
        provider.shutdown()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except ValueError:
        pass  # not the main thread (e.g. under some WSGI servers); skip

    _configured = True
    logger.info('tracing enabled: service=%s endpoint=%s ratio=%s',
                service_name, endpoint, ratio)
    return True


def instrument_flask(app) -> None:
    """No-op unless configure_tracing enabled a provider."""
    if not _configured:
        return
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    FlaskInstrumentor().instrument_app(app)


def instrument_pika() -> None:
    """Instrument all pika channels (publisher inject / consumer extract)."""
    if not _configured:
        return
    from opentelemetry.instrumentation.pika import PikaInstrumentor
    PikaInstrumentor().instrument()
