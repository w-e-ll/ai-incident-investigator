# Presentation outline

This is editable presentation text, not a rendered slide deck. Use the synthetic database incident throughout. Capture actual results after live testing.

## The investigation question

Checkout requests return 502. Is the cause a deployment change, database connection exhaustion, or an unrelated gateway failure?

Show the input and incident window. Explain that the application must connect a possible cause to evidence and identify what is missing.

## Current evidence

The parser preserves timestamps, services, trace identifiers, structured attributes, and source excerpts. Error groups show repeated failures. The timeline helps the engineer inspect event order.

Show a correlated trace and its source records. Event order supports a hypothesis but does not prove causality.

## Historical search

Reviewed cases contain symptoms, root cause, resolution, and verification sections. Those sections become chunks in PostgreSQL. Text search and embedding similarity produce candidates. Reciprocal rank fusion combines their ranks. Tenant and metadata filters restrict the results.

Show the imported case, ready chunks, a relevant match, and a filter that excludes it. No cross-encoder reranker is implemented.

## The model report

The model receives selected current evidence and historical material. It can request more local evidence within a bounded LangGraph loop. The report separates facts, hypotheses, and missing evidence.

Show a completed live run and open its citations. A historical resolution cannot become a fact about the current incident.

## Background execution

The backend reserves a run before paid work. A worker claims a queued job and saves progress. The UI retrieves the result after a refresh.

Show the queued job and completed history entry. A started graph does not resume midway through a provider call. Ambiguous failures need review before another paid attempt.

## Evaluation and cost

Schema checks validate structure. Citation checks validate references and quotes. Neither proves that the diagnosis is correct. Input checks flag some instruction-like text but do not provide a complete prompt-injection defense.

Show evaluation results, measured usage, and estimated investigation cost. The estimate excludes embedding charges and cached-token discounts. A smaller evidence pack alone does not establish cost savings or preserved accuracy.

## Operations

Docker verification passed 60 tests, including PostgreSQL integration. API, UI, Grafana, Prometheus, and Tempo responded to health checks. Application metrics reach Prometheus through the collector.

Show the dashboard and source-attributed logs. Show a Tempo trace only after ingestion is confirmed.

## The next pilot

Test reviewed incidents with known resolutions. Compare hypotheses with the incident review, inspect missed evidence, and record cost and latency. Use those results to decide whether a reranker, broader adapters, or different evidence selection would help.
