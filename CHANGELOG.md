# Changelog

## Unreleased

- Make AI investigation the visible default, with explicit missing-key setup instructions and a clearly labeled rule-based preview.
- Stream real evidence preparation, model call, decision summary, tool result and validation activity to the UI; retain it in report history.
- Preserve report contracts and null fields across streaming and saved-result retrieval.
- Report safe provider authentication/quota/network/schema error categories.
- Render timeline ticks in UTC to match the axis label.

- Fix Compose build targets: migration, API and UI use `runtime`; only verification uses `tests`.
- DockerUp now waits for healthy services and prints diagnostics on startup failure.
- Add DockerStatus and clarify that DockerVerify does not start the application UI.

## 0.1.0 — 2026-10-06

- Initial upload-to-investigation workbench with synthetic scenarios.
- Bounded parsers, redacted evidence provenance, error grouping and timeline.
- Conservative free demo and configurable live LangGraph investigator.
- Strict report models, citation validation, qualitative support and missing evidence.
- Transactional persistence, run history, JSON export and local cost/monitoring views.
- PostgreSQL Compose configuration with Alembic and SQLite local fallback.
- Mocked/domain/API/Streamlit verification; live provider and Docker deployment remain separately scoped checks.


## 2026-10-08

Implemented tenant-scoped repository/API flows, native vector/JSONB migration, hybrid RRF retrieval, knowledge workspace, structured production fixture, durable investigation queue/worker, explicit stale-run recovery, contract evaluation, dated model pricing, rotating module logs, and optional business telemetry. Existing migrations and database volumes are preserved. Docker runtime integration remains unverified when its engine is unavailable.


## Live-test fixes

Corrected corrupted bullet rendering and rerendered the background status control immediately after submission. Strengthened model instructions to separate the observed mechanism from causal triggers found only in historical cases. Added timestamped embedding claims, tenant-scoped stale recovery, and protection against late completion of recovered claims. Recovery never automatically replays paid work.


The saved-result control now checks status before fetching a report. Queued and started jobs show informational messages. Model guidance rejects context-only citations as support for unobserved causal triggers and allows empty current-evidence lists for historical-only hypotheses. These instructions do not constitute semantic validation.

Refresh now restores the selected incident and queued or completed run from IDs in the page URL. Tenant and workspace selections also persist in the URL. Restoration uses tenant-scoped read requests and starts no investigation. The file picker remains empty after refresh, but saved parsed evidence is restored.
