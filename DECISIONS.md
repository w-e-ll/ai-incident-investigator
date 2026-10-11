# Engineering decisions

## 1. Deterministic evidence processing
**Decision:** Python parses, counts, groups and timestamps events before any model call.
**Why:** These observations should be reproducible and testable.
**Tradeoff:** Each supported log format needs explicit parsing; arbitrary tracing exports are not accepted.

## 2. One bounded investigator in LangGraph
**Decision:** Use an explicit prepare/investigate/tool/validate graph and structured LangChain model adapter.
**Why:** Model-driven checks remain visible and bounded, with deterministic validation around them.
**Tradeoff:** No automatic reviewer, unbounded exploration, or durable graph checkpointing.

## 3. Facts / hypotheses / missing evidence
**Decision:** Enforce separate report fields, alternatives, missing evidence, exact quotes and seen IDs.
**Why:** Users must be able to audit claims and uncertainty.
**Tradeoff:** Reference integrity does not verify causal logic; live quality needs evaluation.

## 4. PostgreSQL plus explicit SQLite local fallback
**Decision:** Compose uses PostgreSQL with migrations; native quick start uses SQLite.
**Why:** The first vertical scenario can run without a ready Docker engine.
**Tradeoff:** SQLite test success does not establish PostgreSQL integration. Runtime/migration roles currently share privileges.

## 5. No automatic paid retries
**Decision:** Reserve run UUID before external effects, reuse completed results, reject started/failed replays.
**Why:** Unknown network outcomes must not silently trigger another billable call.
**Tradeoff:** Operators must inspect interrupted runs; no exactly-once billing guarantee.

## 6. Honest demo and cost views
**Decision:** Demo is clearly rule-based; context reduction is a token estimate and cost needs a price snapshot.
**Why:** Demonstrated behavior and measured usage must be distinct from predicted savings.
**Tradeoff:** No live quality benchmark, invoice reconciliation or human-time savings claim in the initial build.


## 2026-10-08

Implemented tenant-scoped repository/API flows, native vector/JSONB migration, hybrid RRF retrieval, knowledge workspace, structured production fixture, durable investigation queue/worker, explicit stale-run recovery, contract evaluation, dated model pricing, rotating module logs, and optional business telemetry. Existing migrations and database volumes are preserved. Docker runtime integration remains unverified when its engine is unavailable.
