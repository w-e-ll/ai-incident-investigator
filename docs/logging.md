# Logging and observability

Backend, worker, and UI use JSON logs. Rotating aggregate logs and module logs are written under `var/logs/<service>/`; each Python module has its own `.log` file. Records include source module/file/line and correlation identifiers where supplied. Model payloads, API keys, and raw uploads are not logged. Structured attributes are redacted before persistence; review uploads because redaction is best effort.

Docker bind-mounts `var/logs` so logs remain inspectable on the host. Files rotate; no centralized log ingestion or retention scheduler is provided. If local file permissions prevent logging, stdout remains available.

`./scripts/run.ps1 ObservabilityUp` uses `compose.observability.yaml` to enable OTLP on API and worker. The collector exports metrics to Prometheus and traces to Tempo. Grafana provisions the application dashboard and datasources. Counters cover completed/failed investigations, provider calls, token usage, HTTP requests, and indexed chunks; histograms cover request/provider duration. Dashboard queries and collector connectivity still require verification against a running Docker engine.
