# Future Sunday AI Builds baseline

For future projects, carry forward these requirements and tailor implementation to the task:

- Python contracts with Pydantic; UI talks to backend over HTTP; credentials remain backend-side.
- PostgreSQL migrations; tenant identity and metadata filters enforced on reads and writes. Public deployments require authenticated tenant authorization.
- Durable jobs with atomic claims, persisted status/progress, bounded timeouts, explicit ambiguous-failure recovery, and no blind retries of paid calls.
- Structured production input samples and meaningful dashboard evidence, timelines, diagnostics, and exports.
- Retrieval where useful: section-aware chunks, embeddings, pgvector, lexical/vector candidate retrieval, reciprocal rank fusion, and optional reranking justified by evaluation.
- Input/output contract checks, citation validation, offline fixtures, honest limits on semantic quality, token usage and dated pricing.
- JSON business-operation logs under var/logs/<service>/<python_file>.log, rotating aggregate logs, source attribution, safe exception handling and correlation IDs.
- Optional OpenTelemetry traces/metrics, Prometheus, Tempo and Grafana with application-level panels.
- Docker startup/health checks, isolated tests, ruff checks, and truthful operational documentation.

This document records the project baseline. It does not automatically modify other repositories or globally install a skill.
