from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from core import telemetry


def test_business_metrics_record_measured_usage(monkeypatch):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://unused:4317")
    monkeypatch.setattr(telemetry, "_instruments", None)
    from opentelemetry import metrics

    monkeypatch.setattr(metrics, "get_meter", provider.get_meter)
    telemetry.record_event("model.completed", {"input_tokens": 20, "output_tokens": 5, "latency_ms": 100})
    telemetry.record_event("run.saved", {"status": "completed"})
    data = reader.get_metrics_data()
    measured = {m.name: m for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics}
    assert sum(p.value for p in measured["investigator_tokens"].data.data_points) == 25
    assert measured["investigator_model_latency_ms"].data.data_points[0].sum == 100
    assert measured["investigator_runs"].data.data_points[0].value == 1
    provider.shutdown()
