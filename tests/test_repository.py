import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from core.parser import parse
from core.schemas import InvestigationError, RunRequest
from db.repository import Repository


def test_concurrent_run_claim_has_one_owner(repository, sample):
    incident = repository.save_incident("sample.jsonl", parse(sample, "jsonl"))
    request = RunRequest(run_id=uuid4())

    def claim():
        try:
            repository.claim(incident.incident_id, request)
            return "claimed"
        except InvestigationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(results) == ["claimed", "run_conflict"]


def test_initial_migration_on_isolated_sqlite(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "incidents",
            "events",
            "investigation_runs",
            "knowledge_chunks",
        }
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_migration_and_repository(monkeypatch, sample):
    supplied = os.getenv("TEST_DATABASE_URL")
    if not supplied:
        pytest.skip("No isolated TEST_DATABASE_URL; PostgreSQL integration was not executed")
    url = make_url(supplied)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to a PostgreSQL database ending in _test")
    schema = "test_" + uuid4().hex
    admin = create_engine(url)
    repository = None
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        scoped = url.update_query_dict({"options": f"-csearch_path={schema},public"})
        monkeypatch.setenv("DATABASE_URL", scoped.render_as_string(hide_password=False))
        command.upgrade(Config("alembic.ini"), "head")
        repository = Repository(scoped.render_as_string(hide_password=False))
        repository.health()
        incident = repository.save_incident("sample.jsonl", parse(sample, "jsonl"))
        assert repository.get_incident(incident.incident_id) == incident
        request = RunRequest(run_id=uuid4())
        repository.claim(incident.incident_id, request)
        with pytest.raises(InvestigationError):
            repository.claim(incident.incident_id, request)
        repository.finish(request.run_id, "failed", {"metrics": {}}, "test_failure")
        assert repository.list_runs()[0].status == "failed"
        vector = [1.0] + [0.0] * 1535
        repository.save_knowledge_chunks(
            [
                {
                    "id": "pg-check",
                    "case_id": "case-1",
                    "tenant_id": "demo-team",
                    "section": "resolution",
                    "ordinal": 0,
                    "text": "database pool timeout rollback",
                    "metadata": {"service": "checkout", "environment": "production"},
                    "embedding": None,
                    "embedding_model": None,
                    "index_status": "queued",
                }
            ]
        )
        batch = repository.claim_queued_chunks("demo-team")
        repository.finish_knowledge_chunks(
            [{**row, "embedding": vector, "embedding_model": "test"} for row in batch], "ready"
        )
        matches = repository.search_knowledge(
            "demo-team", "database timeout", {"service": "checkout"}, query_embedding=vector
        )
        assert len(matches) == 1 and matches[0]["rrf_score"] > 0
        assert repository.search_knowledge("other", "database timeout", {}, query_embedding=vector) == []
        assert (
            repository.search_knowledge(
                "demo-team", "database timeout", {"environment": "staging"}, query_embedding=vector
            )
            == []
        )
    finally:
        if repository:
            repository.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_failed_knowledge_chunks_require_explicit_retry(repository):
    repository.save_knowledge_chunks(
        [
            {
                "id": "tenant-a:case-1:root_cause:0",
                "case_id": "case-1",
                "tenant_id": "tenant-a",
                "section": "root_cause",
                "ordinal": 0,
                "text": "connection pool exhausted",
                "metadata": {"environment": "production"},
                "embedding": None,
                "embedding_model": None,
                "index_status": "queued",
            }
        ]
    )
    claimed = repository.claim_queued_chunks("tenant-a", 20)
    assert len(claimed) == 1
    repository.finish_knowledge_chunks(claimed, "failed")
    assert repository.retry_failed_chunks("other-tenant") == 0
    assert repository.retry_failed_chunks("tenant-a") == 1
    assert repository.claim_queued_chunks("tenant-a", 20)[0]["index_status"] == "embedding"
