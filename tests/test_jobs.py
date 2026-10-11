"""Durable queue tests with isolated SQLite and no provider calls."""

from uuid import uuid4

from core.parser import parse
from core.schemas import RunRequest
from core.settings import Settings
from db.repository import Repository
from worker import process_jobs


def test_queued_job_survives_repository_restart(repository, sample):
    incident = repository.save_incident("sample.jsonl", parse(sample, "jsonl"))
    body = RunRequest(run_id=uuid4(), mode="demo")
    assert repository.enqueue(incident.incident_id, body) == "queued"
    assert repository.enqueue(incident.incident_id, body) == "queued"
    reopened = Repository(str(repository.engine.url))
    try:
        assert process_jobs(reopened, Settings(_env_file=None, openai_api_key="")) == 1
        assert reopened.get_run_row(body.run_id)["status"] == "completed"
        assert process_jobs(reopened, Settings(_env_file=None, openai_api_key="")) == 0
    finally:
        reopened.engine.dispose()


def test_started_job_is_never_automatically_replayed(repository, sample):
    incident = repository.save_incident("sample.jsonl", parse(sample, "jsonl"))
    body = RunRequest(run_id=uuid4(), mode="live")
    repository.enqueue(incident.incident_id, body)
    repository.claim(incident.incident_id, body, from_queue=True)
    assert process_jobs(repository, Settings(_env_file=None, openai_api_key="")) == 0
    assert repository.get_run_row(body.run_id)["status"] == "started"


def test_enqueue_and_status_api(client, sample):
    upload = client.post("/api/v1/incidents", files={"file": ("sample.jsonl", sample)}).json()
    body = {"run_id": str(uuid4()), "mode": "demo"}
    path = f"/api/v1/incidents/{upload['incident_id']}/enqueue"
    response = client.post(path, json=body)
    assert response.status_code == 202 and response.json()["status"] == "queued"
    assert client.get(f"/api/v1/runs/{body['run_id']}/status").json()["status"] == "queued"
    assert client.post(path, json=body).json() == response.json()
    process_jobs(client.app.state.repository, Settings(_env_file=None, openai_api_key=""))
    assert client.get(f"/api/v1/runs/{body['run_id']}").status_code == 200


def test_explicit_stale_run_recovery_never_replays(repository, sample):
    from datetime import timedelta

    from sqlalchemy import update

    from core.schemas import utc_now
    from db.schema import runs

    incident = repository.save_incident("sample.jsonl", parse(sample, "jsonl"))
    body = RunRequest(run_id=uuid4(), mode="live")
    repository.claim(incident.incident_id, body)
    with repository.engine.begin() as connection:
        connection.execute(
            update(runs)
            .where(runs.c.id == str(body.run_id))
            .values(updated_at=utc_now() - timedelta(minutes=16))
        )
    repository.abandon_stale_run(body.run_id, "demo-team")
    row = repository.get_run_row(body.run_id)
    assert row["status"] == "failed" and row["error_code"] == "interrupted_billing_unknown"
    assert process_jobs(repository, Settings(_env_file=None, openai_api_key="")) == 0


def test_stale_embedding_recovery_is_scoped_and_blocks_late_result(repository):
    from datetime import timedelta

    from sqlalchemy import update

    from core.schemas import utc_now
    from db.schema import knowledge_chunks

    rows = [
        dict(
            id=f"{t}:c:symptoms:0",
            case_id="c",
            tenant_id=t,
            section="symptoms",
            ordinal=0,
            text="timeout",
            metadata={},
        )
        for t in ("a", "b")
    ]
    repository.save_knowledge_chunks(rows)
    claimed = repository.claim_queued_chunks("a")
    repository.claim_queued_chunks("b")
    assert repository.recover_stale_embeddings("a") == 0
    with repository.engine.begin() as conn:
        conn.execute(update(knowledge_chunks).values(claimed_at=utc_now() - timedelta(minutes=16)))
    assert repository.recover_stale_embeddings("a") == 1
    assert repository.knowledge_status("b")["embedding"] == 1
    repository.finish_knowledge_chunks(claimed, "ready")
    assert repository.knowledge_status("a")["failed"] == 1
    assert repository.retry_failed_chunks("a") == 1
    assert repository.knowledge_status("a")["queued"] == 1
    assert repository.recover_stale_embeddings("a") == 0


def test_fresh_worker_process_completes_persisted_queue(repository, sample, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    incident = repository.save_incident("sample.jsonl", parse(sample, "jsonl"))
    body = RunRequest(run_id=uuid4(), mode="demo")
    repository.enqueue(incident.incident_id, body)
    env = dict(
        os.environ,
        DATABASE_URL=str(repository.engine.url),
        OPENAI_API_KEY="",
        OTEL_EXPORTER_OTLP_ENDPOINT="",
        LOG_DIR=str(tmp_path / "logs"),
    )
    project = Path(__file__).resolve().parents[1]
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(project / "worker.py"), "--once"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stderr
        assert repository.get_run_row(body.run_id)["status"] == "completed"
    assert len(repository.list_runs()) == 1
