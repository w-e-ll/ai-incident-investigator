# Live investigation contract

## Connection and visible activity

AI mode stays visible even when the backend key is missing; the run button is disabled with explicit .env / container-recreation instructions. A configured key is not a verified connection. Provider authentication (401), permission, quota/rate, timeout, connection and request/schema failures have distinct safe error codes. Provider error bodies and keys are never shown to the user.

`POST /api/v1/incidents/{id}/investigate/stream` emits newline-delimited JSON progress, result or error envelopes. Each progress item represents a real stage transition: evidence selection, model request/response, a short model-authored decision summary, tool query/results, or citation validation. It is an activity record, not a private reasoning transcript. No fake delays, forced tool calls or prerecorded AI steps are used. Final delivery occurs after persistence; saved reports retain the activity list. Old reports without activity remain readable.

The synchronous JSON endpoint remains available. A streaming request runs in a bounded-call, per-run worker thread; if the UI disconnects, the worker attempts to finish and save the run. There is no durable worker queue or crash-resume guarantee. After an interrupted connection, check the run ID before starting again. Errors after streaming begins arrive as explicit error envelopes even though HTTP headers have already reported 200.

Small incident files are parsed into events and selected into an evidence pack. This version does not perform document chunking, embeddings or vector indexing. Correlation by trace ID, literal search and time-window lookup operate directly on uploaded events.

The graph is `prepare → investigate → optional tools → investigate → validate`. One structured model decision selects a tool or returns a report. No multi-agent supervisor or automatic reviewer is used. The four tools are literal search, exact trace lookup, error-group lookup, and aware time-window lookup. They never run shell commands, fetch URLs, or query live infrastructure.

## Bounded inputs

Initial evidence: first/last representatives of up to 20 error groups, selected deployment/configuration markers, neighboring events, and file-boundary context, maximum 60 events. Each model-visible message is truncated to 600 characters. Groups contain count/time/fingerprint metadata; the pack explicitly says it is a sample. Large or omitted groups remain visible in the UI even when excluded from the model pack. Tool results show match count and truncation, maximum 20 events. A matching event outside the returned subset is not evidence the model has seen.

Limits are validated by Pydantic: at most 4 model calls, at most 6 tools (default 4), cumulative input guard up to 32,000 tokens (default 16,000), at most 3,000 output tokens per call (default 2,000). A conservative estimated allowance covers schema/provider overhead. The input guard is not a precise billing cap. Unknown prior usage stops further rounds. The final model call must return a report; a tool request then fails. Exceeding a guard fails transparently rather than silently dropping evidence or retrying a paid call.

Model requests have `max_retries=0` and a 30-second timeout. The UI waits up to 150 seconds. Network timeouts can have an unknown billing outcome. Failure records preserve known token metadata; missing metadata is not zero spend.

## Paid actions and replay

Demo invokes no provider. Live requires a configured backend key and an explicit UI acknowledgement that the upload was reviewed. Run UUID reservation commits before the call. Repeating a completed request with the same UUID and settings reuses the saved report. Same UUID with different settings, started status, or failed status returns a conflict. The UI offers checking the saved result after an unknown HTTP outcome. This is not exactly-once execution or durable recovery.

## Cost and optimization

Estimated usage cost = sum(input tokens × configured input rate + output tokens × configured output rate) / 1,000,000. Decimal arithmetic preserves costs; the API serializes a decimal string. A dated model price snapshot is retained. Cached input discounts, account pricing, invoices, and infrastructure costs are not modeled. Both rates and a date are required; unknown usage/prices produces unknown cost.

Context reduction = (1 − initial evidence-pack token estimate / full redacted-log token estimate) × 100%. Counts use `cl100k_base`, an estimate independent of the configured provider tokenizer. The comparison excludes schema, instructions, symptom, tool rounds and output, and can be negative. No full-log LLM baseline is executed automatically; no dollar or human-time savings is claimed from this comparison.

## Quality evaluation

`samples/ground_truth.json` states the synthetic mechanisms. Evaluate live runs for mechanism identification, citation integrity, relevance of evidence, handling of contradictory evidence, appropriate abstention, alternatives, and next checks that could falsify a hypothesis. Record dataset, model, settings, token usage, cost snapshot and report. Mocked tests validate execution mechanics; they do not establish live accuracy, injection resistance, or optimal model choice.


## Implementation update, 2026-10-08

A PostgreSQL-backed worker now claims queued investigations atomically and persists public progress. LangGraph runs inside each claimed job; no mid-node checkpoint resume or automatic replay of started paid jobs is implemented. Tenant headers scope incident/run/knowledge reads and writes, but are not authentication. Knowledge ingestion is available in the UI, with explicit embedding indexing and failed-item requeue. PostgreSQL search fuses lexical and pgvector candidates with RRF and metadata filters. Automatic historical retrieval uses the symptom or error fingerprints; historical material remains separate from current incident facts. Schema/citation evaluation is persisted, while semantic correctness remains unverified. See README and project-template.md for operational details and boundaries.
