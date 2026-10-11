# Historical incident knowledge base

The knowledge base is tenant-scoped. It stores resolved incident cases as section-aware chunks and keeps embeddings separate from the original incident upload. A ready-to-index fixture is available at `samples/resolved_incident_case.json`.

## Ingestion flow

1. Create chunks with `core.knowledge.chunk_case` from a resolved case containing `symptoms`, `root_cause`, `resolution`, and `verification`.
2. Queue them with `POST /api/v1/knowledge/chunks` and `X-Tenant-ID`.
3. Call `POST /api/v1/knowledge/index` to claim a bounded batch and generate `text-embedding-3-small` vectors.
4. If a batch fails, it is marked `failed`. Retry is explicit:

```http
POST /api/v1/knowledge/retry?limit=20
X-Tenant-ID: demo-team
```

5. Search with `POST /api/v1/knowledge/search`. PostgreSQL uses pgvector plus full-text retrieval fused with reciprocal rank fusion; SQLite uses a deterministic lexical fallback. Metadata filters are applied in both paths.

```json
{
  "query": "checkout database connection timeout",
  "metadata": {"environment": "production", "service": "checkout"},
  "limit": 5
}
```

The investigator automatically performs a tenant-scoped search using the incident symptom and passes the matches to the model as comparative historical context. Historical matches never become citations for current facts; current uploaded events remain the evidence authority.

## Canonical production input

For structured data, upload `incident.v1` JSON. The example is in `samples/incident_v1.json`. It supports `events`, `changes`, timestamps, service, severity, trace/request IDs, deployment operations, and arbitrary structured attributes.

## Implementation update, 2026-10-08

A PostgreSQL-backed worker now claims queued investigations atomically and persists public progress. LangGraph runs inside each claimed job; no mid-node checkpoint resume or automatic replay of started paid jobs is implemented. Tenant headers scope incident/run/knowledge reads and writes, but are not authentication. Knowledge ingestion is available in the UI, with explicit embedding indexing and failed-item requeue. PostgreSQL search fuses lexical and pgvector candidates with RRF and metadata filters. Automatic historical retrieval uses the symptom or error fingerprints; historical material remains separate from current incident facts. Schema/citation evaluation is persisted, while semantic correctness remains unverified. See README and project-template.md for operational details and boundaries.


## Interrupted indexing

Claim timestamps support explicit recovery. In Knowledge base, use Mark stale embedding claims failed after 15 minutes. Recovery marks the selected tenant's old claims failed and does not repeat provider requests. Review provider usage before choosing Requeue failed chunks and indexing again. A late result cannot finalize a recovered claim. Migration 0004 marks legacy in-flight claims failed because their billing status is unknown.
