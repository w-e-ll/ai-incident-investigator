"""Shared investigator service for HTTP streams and durable background jobs."""

from core.embeddings import openai_embedder
from core.investigator import Investigator
from core.logging import emit, logger, run_id
from core.schemas import InvestigationError, RunResponse, utc_now


def execute_investigation(settings, incident_id, body, repository, on_progress=None, from_queue=False):
    token = run_id.set(str(body.run_id))
    runner = None
    claimed = False
    try:
        incident = repository.get_incident(incident_id, body.tenant_id)
        reused = repository.claim(incident_id, body, from_queue=from_queue)
        if reused:
            return reused
        claimed = True
        query = body.symptom or " ".join(g.fingerprint for g in incident.groups[:3])
        query = query[:2000]
        query_embedding = None
        if (
            query
            and body.mode == "live"
            and repository.engine.dialect.name == "postgresql"
            and settings.openai_api_key.get_secret_value()
            and repository.knowledge_status(body.tenant_id)["ready"]
        ):
            query_embedding = openai_embedder(settings.openai_api_key.get_secret_value())([query])[0]
        historical = (
            repository.search_knowledge(
                body.tenant_id, query, body.metadata, limit=8, query_embedding=query_embedding
            )
            if query
            else []
        )
        if historical:
            related = repository.list_knowledge_chunks(body.tenant_id)
            case_ids = {match["case_id"] for match in historical[:3]}
            existing_ids = {match["id"] for match in historical}
            historical += [
                {k: v for k, v in row.items() if k not in {"embedding", "embedding_model", "index_status"}}
                for row in related
                if row["case_id"] in case_ids
                and row["section"] in {"root_cause", "resolution", "verification"}
                and row["index_status"] == "ready"
                and row["id"] not in existing_ids
                and all(str(row["metadata"].get(k)) == v for k, v in body.metadata.items())
            ][:4]
        historical = historical[:10]
        execution = []

        def progress(event):
            execution.append(event.model_dump(mode="json"))
            if from_queue:
                repository.save_progress(body.run_id, execution)
            if on_progress:
                on_progress(event)

        runner = Investigator(
            settings,
            body,
            incident.parsed.events,
            incident.groups,
            on_progress=progress,
            historical_context=historical,
        )
        report, metrics = runner.run()
        response = RunResponse(
            run_id=body.run_id,
            incident_id=incident_id,
            mode=body.mode,
            created_at=utc_now(),
            report=report,
            metrics=metrics,
        )
        repository.finish(body.run_id, "completed", response.model_dump(mode="json"))
        return response
    except Exception as exc:
        if claimed:
            code = exc.code if isinstance(exc, InvestigationError) else "internal_error"
            try:
                repository.finish(
                    body.run_id,
                    "failed",
                    {
                        "metrics": runner.metrics().model_dump(mode="json") if runner else {},
                    },
                    code,
                )
            except Exception:
                logger.exception("run.failure_persistence_failed")
            emit("run.failed", code=code)
        raise
    finally:
        run_id.reset(token)
