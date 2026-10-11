# AI Incident Investigator

AI Incident Investigator helps an engineer examine a small incident log and compare it with resolved incidents. The application groups errors, builds a timeline, and asks a model to propose causes with cited evidence. The report separates observed facts, hypotheses, and missing evidence.

An engineer can upload structured records with spans, metrics, deployment events, and service metadata. The knowledge base stores reviewed historical cases in PostgreSQL. Search combines text matches and embedding similarity, then filters by tenant, service, and environment. A historical fix offers a possible explanation. It does not establish the current cause.

The application records model usage, public investigation activity, and results. A PostgreSQL worker processes queued investigations. Grafana, Prometheus, and OpenTelemetry expose application metrics. Tempo is ready, but trace ingestion has not been confirmed.

Docker verification passed all 60 tests, including PostgreSQL integration. Real embedding retrieval and investigation with historical context still need an end-to-end test. This is a local MVP under verification. Public deployment would require authentication and authorization.

## Short portfolio description

Built an incident investigation application with cited log evidence, historical incident retrieval, tenant filters, a durable investigation queue, and application metrics. Reports keep facts separate from possible causes and missing evidence. Docker verification passed 60 tests, including PostgreSQL integration. Live retrieval and trace ingestion remain under verification.

## Message for a verified live demo

Use this message only after a saved live run confirms indexing, retrieval, and investigation with historical context.

I built AI Incident Investigator for Sunday AI Builds #4. Upload a small incident log, inspect the error timeline, and compare the incident with reviewed historical cases. The report shows evidence behind each fact, possible causes, and the next checks needed to confirm them. The demo uses synthetic data. Model calls and embeddings have a cost, and the application records usage for review.
