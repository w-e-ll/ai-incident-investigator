"""Optional OTel transport and measured business counters."""

import os

_initialized = False
_instruments = None


def configure_telemetry(app=None, engine=None) -> None:
    global _initialized
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if not _initialized:
        resource = Resource.create({"service.name": os.getenv("SERVICE_NAME", "incident-investigator")})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
        metrics.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[
                    PeriodicExportingMetricReader(
                        OTLPMetricExporter(endpoint=endpoint, insecure=True), export_interval_millis=10000
                    )
                ],
            )
        )
        _initialized = True
    if app is not None and not getattr(app, "_otel_ready", False):
        FastAPIInstrumentor.instrument_app(app)
        app._otel_ready = True
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine)


def record_event(event: str, fields: dict) -> None:
    global _instruments
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry import metrics

    if _instruments is None:
        meter = metrics.get_meter("incident-investigator")
        _instruments = {
            "runs": meter.create_counter("investigator_runs"),
            "calls": meter.create_counter("investigator_model_calls"),
            "tokens": meter.create_counter("investigator_tokens"),
            "latency": meter.create_histogram("investigator_model_latency_ms", unit="ms"),
            "http": meter.create_counter("investigator_http_requests"),
            "http_latency": meter.create_histogram("investigator_http_latency_ms", unit="ms"),
            "index": meter.create_counter("investigator_indexed_chunks"),
        }
    if event == "run.saved":
        _instruments["runs"].add(1, {"status": fields.get("status", "unknown")})
    elif event in {"model.completed", "model.failed"}:
        _instruments["calls"].add(1, {"status": event.split(".")[1]})
        for direction in ("input", "output"):
            tokens = fields.get(f"{direction}_tokens")
            if tokens is not None:
                _instruments["tokens"].add(tokens, {"direction": direction})
        if fields.get("latency_ms") is not None:
            _instruments["latency"].record(fields["latency_ms"])
    elif event == "http.request":
        attrs = {"route": fields.get("route", "unmatched"), "status": str(fields.get("status"))}
        _instruments["http"].add(1, attrs)
        _instruments["http_latency"].record(fields["duration_ms"], attrs)
    elif event == "knowledge.indexed":
        _instruments["index"].add(fields.get("events", 0))
