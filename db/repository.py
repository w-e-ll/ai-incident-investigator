"""Reserve before provider calls; never hold a transaction across model execution."""

import json
from datetime import UTC
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, event, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from core.evidence import group_errors
from core.logging import emit
from core.parser import redact
from core.schemas import (
    IncidentSummary,
    InvestigationError,
    Parsed,
    RunRequest,
    RunResponse,
    RunSummary,
    UploadResponse,
    utc_now,
)
from db.schema import events, incidents, knowledge_chunks, metadata, runs


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class Repository:
    def __init__(self, url: str):
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=10000")

            # Explicit local fallback. PostgreSQL is migrated with Alembic before startup.
            metadata.create_all(self.engine)

    def health(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def save_incident(self, name: str, parsed: Parsed, tenant_id: str = "demo-team") -> UploadResponse:
        incident_id = uuid4()
        created = utc_now()
        with self.engine.begin() as connection:
            connection.execute(
                insert(incidents).values(
                    id=str(incident_id),
                    name=name,
                    created_at=created,
                    event_count=len(parsed.events),
                    parse_metadata=parsed.model_dump(mode="json", exclude={"events"}),
                    tenant_id=tenant_id,
                )
            )
            connection.execute(
                insert(events),
                [
                    {"incident_id": str(incident_id), "id": e.id, "payload": e.model_dump(mode="json")}
                    for e in parsed.events
                ],
            )
        emit("incident.saved", incident_id=str(incident_id), events=len(parsed.events))
        return UploadResponse(
            incident_id=incident_id,
            name=name,
            created_at=created,
            parsed=parsed,
            groups=group_errors(parsed.events),
        )

    def get_incident(self, incident_id: UUID, tenant_id: str = "demo-team") -> UploadResponse:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(incidents).where(
                        incidents.c.id == str(incident_id), incidents.c.tenant_id == tenant_id
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise InvestigationError("not_found", "Incident not found", 404)
            payloads = (
                connection.execute(select(events.c.payload).where(events.c.incident_id == str(incident_id)))
                .scalars()
                .all()
            )
        parsed = Parsed.model_validate({**row["parse_metadata"], "events": payloads})
        parsed.events.sort(key=lambda e: e.line_start)
        return UploadResponse(
            incident_id=incident_id,
            name=row["name"],
            created_at=aware(row["created_at"]),
            parsed=parsed,
            groups=group_errors(parsed.events),
        )

    def list_incidents(self, tenant_id: str = "demo-team") -> list[IncidentSummary]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(incidents)
                .where(incidents.c.tenant_id == tenant_id)
                .order_by(incidents.c.created_at.desc())
                .limit(50)
            ).mappings()
            return [
                IncidentSummary(
                    incident_id=r["id"],
                    name=r["name"],
                    created_at=aware(r["created_at"]),
                    event_count=r["event_count"],
                )
                for r in rows
            ]

    def save_knowledge_chunks(self, chunks: list[dict]) -> int:
        """Persist chunks before embeddings; each row is tenant-scoped and indexable later."""
        if not chunks:
            return 0
        insert_fn = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        count = 0
        with self.engine.begin() as connection:
            for chunk in chunks:
                existing = (
                    connection.execute(select(knowledge_chunks).where(knowledge_chunks.c.id == chunk["id"]))
                    .mappings()
                    .first()
                )
                if existing and any(
                    existing[key] != chunk[key]
                    for key in ("case_id", "tenant_id", "section", "ordinal", "text", "metadata")
                ):
                    raise InvestigationError(
                        "case_conflict", "This case version already exists with different content", 409
                    )
                result = connection.execute(
                    insert_fn(knowledge_chunks).values(**chunk).on_conflict_do_nothing(index_elements=["id"])
                )
                count += result.rowcount
        emit("knowledge.chunks_saved", events=count)
        return count

    def list_knowledge_chunks(self, tenant_id: str, case_id: str | None = None) -> list[dict]:
        """Never return chunks outside the requested tenant."""
        condition = knowledge_chunks.c.tenant_id == tenant_id
        if case_id:
            condition = condition & (knowledge_chunks.c.case_id == case_id)
        with self.engine.connect() as connection:
            return [
                dict(row) for row in connection.execute(select(knowledge_chunks).where(condition)).mappings()
            ]

    def claim_queued_chunks(self, tenant_id: str, limit: int = 20) -> list[dict]:
        """Claim a bounded tenant-scoped batch before provider work."""
        claimed_at = utc_now()
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(knowledge_chunks)
                    .where(
                        knowledge_chunks.c.tenant_id == tenant_id, knowledge_chunks.c.index_status == "queued"
                    )
                    .order_by(knowledge_chunks.c.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            ids = [row["id"] for row in rows]
            if ids:
                claimed = (
                    connection.execute(
                        update(knowledge_chunks)
                        .where(knowledge_chunks.c.id.in_(ids), knowledge_chunks.c.index_status == "queued")
                        .values(index_status="embedding", claimed_at=claimed_at)
                        .returning(knowledge_chunks.c.id)
                    )
                    .scalars()
                    .all()
                )
                rows = [row for row in rows if row["id"] in claimed]
        return [{**dict(row), "index_status": "embedding", "claimed_at": claimed_at} for row in rows]

    def retry_failed_chunks(self, tenant_id: str, limit: int = 20) -> int:
        """Explicitly requeue failed embeddings for one tenant."""
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(knowledge_chunks.c.id)
                    .where(
                        knowledge_chunks.c.tenant_id == tenant_id,
                        knowledge_chunks.c.index_status == "failed",
                    )
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            if rows:
                connection.execute(
                    update(knowledge_chunks)
                    .where(knowledge_chunks.c.id.in_(rows))
                    .values(index_status="queued", claimed_at=None)
                )
        return len(rows)

    def recover_stale_embeddings(self, tenant_id: str) -> int:
        """Fail old claims without replaying ambiguous paid work."""
        from datetime import timedelta

        with self.engine.begin() as connection:
            ids = (
                connection.execute(
                    update(knowledge_chunks)
                    .where(
                        knowledge_chunks.c.tenant_id == tenant_id,
                        knowledge_chunks.c.index_status == "embedding",
                        knowledge_chunks.c.claimed_at < utc_now() - timedelta(minutes=15),
                    )
                    .values(index_status="failed")
                    .returning(knowledge_chunks.c.id)
                )
                .scalars()
                .all()
            )
        return len(ids)

    def finish_knowledge_chunks(self, chunks: list[dict], status: str) -> None:
        with self.engine.begin() as connection:
            for chunk in chunks:
                values = {"index_status": status}
                if "embedding" in chunk:
                    values.update(embedding=chunk["embedding"], embedding_model=chunk.get("embedding_model"))
                connection.execute(
                    update(knowledge_chunks)
                    .where(
                        knowledge_chunks.c.id == chunk["id"],
                        knowledge_chunks.c.index_status == "embedding",
                        knowledge_chunks.c.claimed_at == chunk.get("claimed_at"),
                    )
                    .values(**values)
                )

    def knowledge_status(self, tenant_id: str) -> dict[str, int]:
        """Return tenant-scoped indexing counters for operational dashboards."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(knowledge_chunks.c.index_status, func.count())
                .where(knowledge_chunks.c.tenant_id == tenant_id)
                .group_by(knowledge_chunks.c.index_status)
            ).all()
        result = {"queued": 0, "embedding": 0, "ready": 0, "failed": 0}
        result.update({str(status): int(count) for status, count in rows})
        return result

    def search_knowledge(
        self,
        tenant_id: str,
        query: str,
        metadata: dict[str, str],
        limit: int = 5,
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        """Use PostgreSQL hybrid search when an embedding is available; otherwise lexical fallback."""
        if self.engine.dialect.name == "postgresql" and query_embedding:
            from core.hybrid_search import HYBRID_SQL, vector_literal

            with self.engine.connect() as connection:
                rows = (
                    connection.execute(
                        text(HYBRID_SQL),
                        {
                            "query": query,
                            "tenant_id": tenant_id,
                            "embedding": vector_literal(query_embedding),
                            "metadata": json.dumps(metadata),
                            "limit": limit,
                        },
                    )
                    .mappings()
                    .all()
                )
            return [{**dict(row), "rrf_score": float(row["rrf_score"])} for row in rows]
        needle = query.casefold()
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(knowledge_chunks).where(
                        knowledge_chunks.c.tenant_id == tenant_id, knowledge_chunks.c.index_status == "ready"
                    )
                )
                .mappings()
                .all()
            )
        candidates = []
        for row in rows:
            if any(str(row["metadata"].get(key)) != value for key, value in metadata.items()):
                continue
            score = sum(1 for term in needle.split() if term in row["text"].casefold())
            if score:
                candidates.append((score, str(row["id"]), dict(row)))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [
            {
                **{k: v for k, v in row.items() if k not in {"embedding", "embedding_model", "index_status"}},
                "lexical_score": score,
                "vector_score": None,
                "rrf_score": 1 / (60 + rank),
            }
            for rank, (score, _, row) in enumerate(candidates[:limit], 1)
        ]

    def get_run_row(self, run_id: UUID, tenant_id: str = "demo-team") -> dict | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(runs)
                    .join(incidents, runs.c.incident_id == incidents.c.id)
                    .where(runs.c.id == str(run_id), incidents.c.tenant_id == tenant_id)
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def enqueue(self, incident_id: UUID, request: RunRequest) -> str:
        self.get_incident(incident_id, request.tenant_id)
        config = request.model_dump(mode="json")
        config["symptom"] = redact(config["symptom"])
        existing = self.get_run_row(request.run_id, request.tenant_id)
        if existing:
            if existing["incident_id"] != str(incident_id) or existing["config"] != config:
                raise InvestigationError("run_conflict", "Run ID belongs to a different request", 409)
            return existing["status"]
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(runs).values(
                        id=str(request.run_id),
                        incident_id=str(incident_id),
                        status="queued",
                        mode=request.mode,
                        created_at=utc_now(),
                        updated_at=utc_now(),
                        config=config,
                    )
                )
        except IntegrityError as exc:
            raise InvestigationError("run_conflict", "Run already queued", 409) from exc
        emit("run.queued", mode=request.mode)
        return "queued"

    def queued_runs(self, limit: int = 20) -> list[dict]:
        with self.engine.connect() as connection:
            return [
                dict(r)
                for r in connection.execute(
                    select(runs).where(runs.c.status == "queued").order_by(runs.c.created_at).limit(limit)
                ).mappings()
            ]

    def save_progress(self, run_id: UUID, execution: list[dict]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(runs)
                .where(runs.c.id == str(run_id), runs.c.status == "started")
                .values(payload={"execution": execution[-60:]}, updated_at=utc_now())
            )

    def claim(self, incident_id: UUID, request: RunRequest, from_queue: bool = False) -> RunResponse | None:
        config = request.model_dump(mode="json")
        config["symptom"] = redact(config["symptom"])
        self.get_incident(incident_id, request.tenant_id)
        existing = self.get_run_row(request.run_id, request.tenant_id)
        if existing:
            if existing["incident_id"] != str(incident_id) or existing["config"] != config:
                raise InvestigationError("run_conflict", "Run ID belongs to a different request", 409)
            if existing["status"] == "queued" and from_queue:
                with self.engine.begin() as connection:
                    result = connection.execute(
                        update(runs)
                        .where(runs.c.id == str(request.run_id), runs.c.status == "queued")
                        .values(status="started", updated_at=utc_now())
                    )
                    if result.rowcount != 1:
                        raise InvestigationError("run_conflict", "Job already claimed", 409)
                emit("run.claimed", mode=request.mode)
                return None
            if existing["status"] == "completed":
                emit("run.reused")
                return RunResponse.model_validate(existing["payload"])
            raise InvestigationError(
                "run_conflict", "Run already started or failed; inspect history before a new run", 409
            )
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(runs).values(
                        id=str(request.run_id),
                        incident_id=str(incident_id),
                        status="started",
                        mode=request.mode,
                        created_at=utc_now(),
                        updated_at=utc_now(),
                        config=config,
                    )
                )
        except IntegrityError as exc:
            raise InvestigationError("run_conflict", "Run already claimed", 409) from exc
        emit("run.claimed", mode=request.mode)
        return None

    def abandon_stale_run(self, run_id: UUID, tenant_id: str) -> None:
        from datetime import timedelta

        cutoff = utc_now() - timedelta(minutes=15)
        row = self.get_run_row(run_id, tenant_id)
        if row is None:
            raise InvestigationError("not_found", "Run not found", 404)
        if row["status"] != "started" or aware(row["updated_at"]) > cutoff:
            raise InvestigationError(
                "run_active", "Only started runs inactive for at least 15 minutes can be abandoned", 409
            )
        with self.engine.begin() as connection:
            result = connection.execute(
                update(runs)
                .where(runs.c.id == str(run_id), runs.c.status == "started", runs.c.updated_at <= cutoff)
                .values(status="failed", updated_at=utc_now(), error_code="interrupted_billing_unknown")
            )
            if result.rowcount != 1:
                raise InvestigationError("run_conflict", "Run changed during recovery", 409)
        emit("run.abandoned", billing_status="unknown", tenant_id=tenant_id)

    def finish(self, run_id: UUID, status: str, payload: dict, error_code: str | None = None) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(runs)
                .where(
                    runs.c.id == str(run_id),
                    runs.c.status == "started",
                )
                .values(status=status, payload=payload, updated_at=utc_now(), error_code=error_code)
            )
            if result.rowcount != 1:
                raise InvestigationError("run_conflict", "Run cannot be finalized", 409)
        emit("run.saved", status=status)

    def list_runs(self, tenant_id: str = "demo-team") -> list[RunSummary]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(runs)
                .join(incidents, runs.c.incident_id == incidents.c.id)
                .where(incidents.c.tenant_id == tenant_id)
                .order_by(runs.c.created_at.desc())
                .limit(100)
            ).mappings()
            return [
                RunSummary(
                    run_id=r["id"],
                    incident_id=r["incident_id"],
                    status=r["status"],
                    mode=r["mode"],
                    created_at=aware(r["created_at"]),
                    error_code=r["error_code"],
                    duration_ms=(r["payload"] or {}).get("metrics", {}).get("duration_ms"),
                )
                for r in rows
            ]
