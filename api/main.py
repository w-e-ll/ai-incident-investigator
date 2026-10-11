"""FastAPI owns configuration, persistence, external calls, and safe error translation."""

import re
from contextlib import asynccontextmanager
from contextvars import copy_context
from queue import SimpleQueue
from threading import Thread
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from core.embeddings import embed_chunks, openai_embedder
from core.incident_bundle import parse_bundle
from core.logging import emit, logger, request_id, setup_logging
from core.parser import MAX_BYTES, parse, redact, redact_attributes
from core.schemas import (
    APIError,
    Contract,
    IncidentSummary,
    InvestigationError,
    InvestigationUpdate,
    KnowledgeChunkBatch,
    KnowledgeSearchRequest,
    RunRequest,
    RunResponse,
    RunSummary,
    UploadResponse,
)
from core.service import execute_investigation
from core.settings import Settings
from core.telemetry import configure_telemetry
from db.repository import Repository


class Health(Contract):
    status: str


class Capabilities(Contract):
    live_configured: bool
    model: str
    storage: str
    max_upload_bytes: int
    pricing_configured: bool
    live_status: str
    live_setup: str | None


def create_app(settings: Settings | None = None, repository: Repository | None = None) -> FastAPI:
    settings = settings or Settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app):
        app.state.repository = repository or Repository(settings.database_url)
        app.state.repository.health()
        configure_telemetry(engine=app.state.repository.engine)
        yield
        if repository is None:
            app.state.repository.engine.dispose()

    app = FastAPI(title="AI Incident Investigator", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def context(request: Request, call_next):
        token = request_id.set(str(uuid4()))
        started = perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id.get()
            route = getattr(request.scope.get("route"), "path", "unmatched")
            emit(
                "http.request",
                route=route,
                method=request.method,
                status=response.status_code,
                duration_ms=(perf_counter() - started) * 1000,
            )
            return response
        finally:
            request_id.reset(token)

    def error_response(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content=APIError(
                code=code,
                message=message,
                request_id=request_id.get(),
            ).model_dump(),
        )

    @app.exception_handler(InvestigationError)
    async def domain_error(request, exc):
        emit("operation.rejected", code=exc.code, status=exc.status)
        return error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        emit("http.validation_error", status=422)
        return error_response("validation_error", "Invalid request fields or limits", 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error("database.unavailable", exc_info=(type(exc), exc, exc.__traceback__))
        return error_response("database_unavailable", "Storage is unavailable", 503)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logger.error("http.unhandled_error", exc_info=(type(exc), exc, exc.__traceback__))
        return error_response("internal_error", "Unexpected error; check backend logs using request ID", 500)

    @app.get("/health", response_model=Health)
    def health():
        return Health(status="ok")

    @app.get("/health/db", response_model=Health)
    def health_db(request: Request):
        request.app.state.repository.health()
        return Health(status="ok")

    @app.get("/api/v1/config", response_model=Capabilities)
    def config():
        return Capabilities(
            live_configured=bool(settings.openai_api_key.get_secret_value()),
            live_status="key_configured_not_verified"
            if settings.openai_api_key.get_secret_value()
            else "missing_api_key",
            live_setup=None
            if settings.openai_api_key.get_secret_value()
            else "Set OPENAI_API_KEY in the project .env, then recreate the API container with DockerUp.",
            model=settings.investigation_model,
            storage="SQLite local fallback" if settings.database_url.startswith("sqlite") else "PostgreSQL",
            max_upload_bytes=MAX_BYTES,
            pricing_configured=(
                settings.input_usd_per_million is not None
                and settings.output_usd_per_million is not None
                and bool(settings.price_as_of)
            ),
        )

    def tenant(request: Request, fallback: str = "demo-team") -> str:
        value = request.headers.get("X-Tenant-ID", fallback)
        if len(value) > 100 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value):
            raise InvestigationError("tenant_invalid", "Invalid tenant identifier")
        return value

    @app.post("/api/v1/incidents", response_model=UploadResponse, status_code=201)
    async def upload(request: Request, file: Annotated[UploadFile, File()]):
        name = file.filename or "upload"
        try:
            extension = name.rsplit(".", 1)[-1].lower()
            if extension not in {"jsonl", "json", "log", "txt"}:
                raise InvestigationError("format", "Supported extensions: .json, .jsonl, .log, .txt")
            data = await file.read(MAX_BYTES + 1)
            parsed = (
                await run_in_threadpool(parse_bundle, data)
                if extension == "json"
                else await run_in_threadpool(parse, data, "jsonl" if extension == "jsonl" else "text")
            )
            safe_name = re.sub(r"[^\w. -]", "_", name.replace("\\", "/").rsplit("/", 1)[-1])[:160]
            tenant_id = tenant(request)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", tenant_id):
                raise InvestigationError("tenant_invalid", "Invalid tenant identifier")
            emit(
                "upload.parsed",
                events=len(parsed.events),
                rejected=parsed.rejected_records,
                tenant_id=tenant_id,
            )
            return await run_in_threadpool(
                request.app.state.repository.save_incident, safe_name, parsed, tenant_id
            )
        finally:
            await file.close()

    @app.post("/api/v1/knowledge/chunks", response_model=dict)
    def queue_knowledge_chunks(body: KnowledgeChunkBatch, request: Request):
        tenant_id = tenant(request, body.tenant_id)
        rows = [
            {
                "id": f"{tenant_id}:{chunk.id}",
                "case_id": chunk.case_id,
                "tenant_id": tenant_id,
                "section": chunk.section,
                "ordinal": chunk.ordinal,
                "text": redact(chunk.text),
                "metadata": redact_attributes(chunk.metadata),
                "embedding": None,
                "embedding_model": None,
                "index_status": "queued",
            }
            for chunk in body.chunks
        ]
        count = request.app.state.repository.save_knowledge_chunks(rows)
        return {"status": "queued", "tenant_id": tenant_id, "count": count}

    @app.post("/api/v1/knowledge/recover", response_model=dict)
    def recover_knowledge(request: Request):
        tenant_id = tenant(request)
        count = request.app.state.repository.recover_stale_embeddings(tenant_id)
        emit("knowledge.stale_failed", tenant_id=tenant_id, events=count)
        return {"failed": count, "billing_status": "unknown", "automatic_retry": False}

    @app.post("/api/v1/knowledge/retry", response_model=dict)
    def retry_knowledge(request: Request, limit: int = 20):
        if not 1 <= limit <= 100:
            raise InvestigationError("limit_invalid", "Retry limit must be between 1 and 100")
        tenant_id = tenant(request)
        count = request.app.state.repository.retry_failed_chunks(tenant_id, limit)
        emit("knowledge.retry_queued", tenant_id=tenant_id, events=count)
        return {"status": "queued" if count else "idle", "tenant_id": tenant_id, "requeued": count}

    @app.post("/api/v1/knowledge/index", response_model=dict)
    def index_knowledge(request: Request):
        tenant_id = tenant(request)
        if not settings.openai_api_key.get_secret_value():
            raise InvestigationError("key_missing", "Configure OPENAI_API_KEY before indexing", 503)
        rows = request.app.state.repository.claim_queued_chunks(tenant_id, 20)
        if not rows:
            return {"status": "idle", "tenant_id": tenant_id, "processed": 0}
        try:
            ready = embed_chunks(rows, openai_embedder(settings.openai_api_key.get_secret_value()))
            request.app.state.repository.finish_knowledge_chunks(ready, "ready")
        except Exception as exc:
            request.app.state.repository.finish_knowledge_chunks(rows, "failed")
            raise InvestigationError(
                "embedding_failed", "Embedding job failed; inspect logs before explicit retry", 502
            ) from exc
        emit("knowledge.indexed", tenant_id=tenant_id, events=len(ready))
        return {
            "status": "ready",
            "tenant_id": tenant_id,
            "processed": len(ready),
            "model": "text-embedding-3-small",
        }

    @app.get("/api/v1/knowledge/status", response_model=dict)
    def knowledge_status(request: Request):
        tenant_id = tenant(request)
        return {"tenant_id": tenant_id, "counts": request.app.state.repository.knowledge_status(tenant_id)}

    @app.post("/api/v1/knowledge/search", response_model=list[dict])
    def search_knowledge(body: KnowledgeSearchRequest, request: Request):
        tenant_id = tenant(request)
        query_embedding = None
        if (
            request.app.state.repository.engine.dialect.name == "postgresql"
            and settings.openai_api_key.get_secret_value()
        ):
            query_embedding = openai_embedder(settings.openai_api_key.get_secret_value())([body.query])[0]
        return request.app.state.repository.search_knowledge(
            tenant_id, body.query, body.metadata, body.limit, query_embedding
        )

    @app.get("/api/v1/incidents", response_model=list[IncidentSummary])
    def incidents(request: Request):
        return request.app.state.repository.list_incidents(tenant(request))

    @app.get("/api/v1/incidents/{incident_id}", response_model=UploadResponse)
    def incident(incident_id: UUID, request: Request):
        return request.app.state.repository.get_incident(incident_id, tenant(request))

    @app.post("/api/v1/incidents/{incident_id}/enqueue", status_code=202, response_model=dict)
    def enqueue(incident_id: UUID, body: RunRequest, request: Request):
        body = body.model_copy(update={"tenant_id": tenant(request, body.tenant_id)})
        status = request.app.state.repository.enqueue(incident_id, body)
        return {"run_id": str(body.run_id), "incident_id": str(incident_id), "status": status}

    @app.post("/api/v1/runs/{investigation_id}/abandon", response_model=dict)
    def abandon_run(investigation_id: UUID, request: Request):
        request.app.state.repository.abandon_stale_run(investigation_id, tenant(request))
        return {"run_id": str(investigation_id), "status": "failed", "billing_status": "unknown"}

    @app.get("/api/v1/runs/{investigation_id}/status", response_model=dict)
    def job_status(investigation_id: UUID, request: Request):
        row = request.app.state.repository.get_run_row(investigation_id, tenant(request))
        if row is None:
            raise InvestigationError("not_found", "Run not found", 404)
        return {
            "run_id": row["id"],
            "status": row["status"],
            "error_code": row["error_code"],
            "execution": (row["payload"] or {}).get("execution", []),
        }

    @app.post("/api/v1/incidents/{incident_id}/investigate", response_model=RunResponse)
    def investigate(incident_id: UUID, body: RunRequest, request: Request):
        body = body.model_copy(update={"tenant_id": tenant(request, body.tenant_id)})
        return execute_investigation(settings, incident_id, body, request.app.state.repository)

    @app.post("/api/v1/incidents/{incident_id}/investigate/stream", response_class=StreamingResponse)
    def stream_investigation(incident_id: UUID, body: RunRequest, request: Request):
        """Stream actual progress. Work continues to persistence if the client disconnects."""
        body = body.model_copy(update={"tenant_id": tenant(request, body.tenant_id)})
        repository = request.app.state.repository
        repository.get_incident(incident_id, body.tenant_id)
        context = copy_context()
        updates = SimpleQueue()

        def work():
            try:
                result = execute_investigation(
                    settings,
                    incident_id,
                    body,
                    repository,
                    on_progress=lambda event: updates.put(InvestigationUpdate(type="progress", event=event)),
                )
                updates.put(InvestigationUpdate(type="result", result=result))
            except Exception as exc:
                if isinstance(exc, InvestigationError):
                    code, message = exc.code, exc.message
                elif isinstance(exc, SQLAlchemyError):
                    code, message = "database_unavailable", "Storage is unavailable"
                    logger.exception("stream.database_unavailable")
                else:
                    code, message = "internal_error", "Unexpected investigation error; check backend logs"
                    logger.exception("stream.unhandled_error")
                updates.put(
                    InvestigationUpdate(
                        type="error",
                        error=APIError(
                            code=code,
                            message=message,
                            request_id=request_id.get(),
                        ),
                    )
                )
            finally:
                updates.put(None)

        def lines():
            Thread(target=context.run, args=(work,), daemon=True, name="investigation-stream").start()
            while (update := updates.get()) is not None:
                yield update.model_dump_json() + "\n"

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/runs", response_model=list[RunSummary])
    def runs(request: Request):
        return request.app.state.repository.list_runs(tenant(request))

    @app.get("/api/v1/runs/{investigation_id}", response_model=RunResponse)
    def result(investigation_id: UUID, request: Request):
        row = request.app.state.repository.get_run_row(investigation_id, tenant(request))
        if row is None:
            raise InvestigationError("not_found", "Run not found", 404)
        if row["status"] != "completed":
            raise InvestigationError("run_incomplete", f"Run status: {row['status']}; inspect history", 409)
        return RunResponse.model_validate(row["payload"])

    configure_telemetry(app=app)
    return app


app = create_app()
