import os

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
except ImportError:
    trace = None


def setup_opentelemetry(app):
    if trace is None:
        return

    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "annaseo")})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()
