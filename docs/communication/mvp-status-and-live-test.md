# MVP status and live test

Status recorded on 2026-10-08. Readiness checks and completed tests are distinct from pending live verification.

## Verified

The user's Docker verification passed all 60 tests, including PostgreSQL integration. Database initialization and Alembic migrations completed. API database health and Streamlit health returned HTTP 200. Grafana and Prometheus responded. Prometheus reported the collector target as up. The collector exposed application HTTP metrics. Tempo readiness returned HTTP 200 after the configuration correction.

## Pending

Record a live test for embedding indexing, hybrid retrieval, historical context in investigation, and queued live results. Tempo search returned no traces at the last check. Readiness alone does not verify ingestion.

## Limits

Tenant headers scope data but do not authenticate a caller. The worker persists queued investigations and progress. Started LangGraph execution does not resume midway through a provider call. Recovery for stale embedding work remains unfinished. Injection checks are advisory. Schema and citation checks do not provide a grounding score or establish semantic correctness. Dedicated external observability adapters and a cross-encoder reranker are not implemented.

## Start the stack

Run in the project directory.

```powershell
.\scripts\run.ps1 DockerUp
.\scripts\run.ps1 ObservabilityUp
docker compose --profile observability ps -a
```

Open http://127.0.0.1:8501. Use synthetic data and keep the same tenant during case import and investigation.

## Check retrieval

1. Open Knowledge base and choose the synthetic resolved case.
2. Preview chunks and metadata. Save the case to the queue.
3. Review the data and authorize embeddings. Indexing makes paid requests.
4. Confirm ready chunks and record any failed items.
5. Search for database connection timeouts and inspect returned sections.
6. Apply matching service and environment filters. Apply a mismatching filter and confirm the case disappears.

## Check investigation

1. Load production_trace_incident.json.
2. Choose AI investigation and enter the observed symptom.
3. Match historical filters to case metadata.
4. Review evidence and authorize the provider request. Keep the model-call limit at three.
5. Run the investigation and export its JSON.
6. Check token usage, historical matches, citations, hypotheses, missing evidence, and evaluation results.

Zero tool calls can be valid when initial evidence is sufficient. Historical resolutions must not appear as observed facts about the current incident.

## Check the worker

Submit another investigation with background execution selected. Check status, refresh the browser, and retrieve the saved result. Avoid interrupting a paid request during this first test.

## Check observability

Open http://127.0.0.1:3000 and select the last 15 minutes. Generate application activity, then inspect requests, model calls, tokens, and latency. Check the collector at http://127.0.0.1:9090/targets. In Grafana Explore, select Tempo and search for service api. Save a trace identifier only when a trace is returned.

## Record results

Save the investigation export, historical search result, dashboard screenshots, errors, sample name, tenant, filters, model, and test time. Do not share .env or keys. Do not delete the database volume for troubleshooting.

| Check | Result |
|---|---|
| Docker and PostgreSQL tests | Passed, 60 tests |
| Application and monitoring health | Passed |
| OTel metrics reach Prometheus | Passed |
| Tempo readiness | Passed |
| Tempo trace ingestion | Observed in user screenshots, 2026-10-10 |
| Real embedding indexing and retrieval | User demonstrated ready chunks and matching filtered retrieval |
| Live investigation with historical context | Observed in exported report and user screenshots |
| Queued live result survives browser refresh | User confirmed restored incident and findings |

Update pending rows with observed results. Do not mark the MVP ready because containers started.
