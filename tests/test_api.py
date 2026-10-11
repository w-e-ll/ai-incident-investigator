import json
from uuid import uuid4


def upload(client, sample):
    response = client.post("/api/v1/incidents", files={"file": ("sample.jsonl", sample)})
    assert response.status_code == 201
    return response.json()["incident_id"]


def test_upload_investigate_reuse_and_history(client, sample):
    incident_id = upload(client, sample)
    body = {"run_id": str(uuid4()), "mode": "demo"}
    path = f"/api/v1/incidents/{incident_id}/investigate"
    first = client.post(path, json=body)
    assert first.status_code == 200
    assert first.json()["metrics"]["evidence_validated"]
    assert client.post(path, json=body).json() == first.json()
    assert len(client.get("/api/v1/runs").json()) == 1
    assert client.get(f"/api/v1/runs/{body['run_id']}").json() == first.json()
    conflict = client.post(path, json={**body, "symptom": "different"})
    assert conflict.status_code == 409


def test_live_missing_key_saved_as_failure(client, sample):
    incident_id = upload(client, sample)
    response = client.post(
        f"/api/v1/incidents/{incident_id}/investigate", json={"run_id": str(uuid4()), "mode": "live"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "key_missing"
    row = client.get("/api/v1/runs").json()[0]
    assert row["status"] == "failed" and row["error_code"] == "key_missing"


def test_validation_safe_error(client):
    response = client.get("/api/v1/incidents/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "traceback" not in response.text.lower()


def test_not_found_and_health(client):
    assert client.get("/health/db").status_code == 200
    assert client.get(f"/api/v1/incidents/{uuid4()}").status_code == 404
    assert client.get("/api/v1/config").json()["live_configured"] is False


def test_invalid_upload_and_limits(client):
    assert client.post("/api/v1/incidents", files={"file": ("x.jsonl", b"bad")}).status_code == 422
    assert client.post("/api/v1/incidents", files={"file": ("x.exe", b"bad")}).status_code == 422


def test_failed_run_not_replayed(client, sample):
    incident_id = upload(client, sample)
    body = {"run_id": str(uuid4()), "mode": "live"}
    path = f"/api/v1/incidents/{incident_id}/investigate"
    client.post(path, json=body)
    assert client.post(path, json=body).status_code == 409


def test_progress_stream_persists_real_demo_events_and_reuses_result(client, sample):
    incident_id = upload(client, sample)
    body = {"run_id": str(uuid4()), "mode": "demo"}
    path = f"/api/v1/incidents/{incident_id}/investigate/stream"
    response = client.post(path, json=body)
    updates = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert updates[0]["event"]["stage"] == "prepare"
    assert updates[-1]["type"] == "result"
    result = updates[-1]["result"]
    assert all(item["event"]["stage"] != "model" for item in updates[:-1])
    assert result["metrics"]["execution"] == [item["event"] for item in updates[:-1]]
    assert client.get(f"/api/v1/runs/{body['run_id']}").json() == result
    replay = client.post(path, json=body)
    assert len(replay.text.splitlines()) == 1
    assert json.loads(replay.text)["result"] == result


def test_progress_stream_failure_is_explicit_and_safe(client, sample):
    incident_id = upload(client, sample)
    response = client.post(
        f"/api/v1/incidents/{incident_id}/investigate/stream", json={"run_id": str(uuid4()), "mode": "live"}
    )
    updates = [json.loads(line) for line in response.text.splitlines()]
    assert updates[-1]["type"] == "error"
    assert updates[-1]["error"]["code"] == "key_missing"
    assert updates[-1]["error"]["request_id"] == response.headers["X-Request-ID"]
    assert not any(item["type"] == "result" for item in updates)
    assert client.get("/api/v1/runs").json()[0]["status"] == "failed"


def test_upload_incident_v1_bundle(client):
    payload = {
        "schema_version": "incident.v1",
        "incident_id": "checkout-1",
        "service": "checkout",
        "events": [
            {
                "timestamp": "2026-10-07T12:00:00Z",
                "service": "database",
                "severity": "WARNING",
                "message": "connection pool exhausted",
                "attributes": {"active_connections": 20},
            }
        ],
        "changes": [],
    }
    response = client.post(
        "/api/v1/incidents",
        files={"file": ("incident.json", json.dumps(payload), "application/json")},
        headers={"X-Tenant-ID": "tenant-a"},
    )
    assert response.status_code == 201
    incident = response.json()
    assert len(incident["parsed"]["events"]) == 1
    assert client.get("/api/v1/incidents", headers={"X-Tenant-ID": "tenant-a"}).status_code == 200


def test_knowledge_status_is_tenant_scoped(client):
    assert client.get("/api/v1/knowledge/status", headers={"X-Tenant-ID": "tenant-a"}).json()["counts"] == {
        "queued": 0,
        "embedding": 0,
        "ready": 0,
        "failed": 0,
    }


def test_incident_and_run_tenant_boundaries(client, sample):
    headers = {"X-Tenant-ID": "team-a"}
    response = client.post("/api/v1/incidents", files={"file": ("sample.jsonl", sample)}, headers=headers)
    incident_id = response.json()["incident_id"]
    path = f"/api/v1/incidents/{incident_id}"
    assert client.get(path).status_code == 404
    assert client.get(path, headers=headers).status_code == 200
    assert client.get("/api/v1/incidents").json() == []
    assert len(client.get("/api/v1/incidents", headers=headers).json()) == 1
    body = {"run_id": str(uuid4()), "mode": "demo", "symptom": "database timeout"}
    assert client.post(path + "/investigate", json=body).status_code == 404
    run = client.post(path + "/investigate", json=body, headers=headers)
    assert run.status_code == 200
    assert client.get("/api/v1/runs").json() == []
    assert client.get(f"/api/v1/runs/{body['run_id']}").status_code == 404
    assert client.get(f"/api/v1/runs/{body['run_id']}", headers=headers).status_code == 200
    assert client.post(path + "/investigate/stream", json=body).status_code == 404


def test_knowledge_import_index_search_and_retry(client, monkeypatch):
    from core.embeddings import EMBEDDING_DIMENSIONS

    headers = {"X-Tenant-ID": "team-a"}
    payload = {
        "tenant_id": "team-a",
        "chunks": [
            {
                "id": "case-1:resolution:0",
                "case_id": "case-1",
                "section": "resolution",
                "ordinal": 0,
                "text": "database timeout resolved by rollback",
                "metadata": {"service": "checkout", "environment": "production"},
            }
        ],
    }
    assert client.post("/api/v1/knowledge/chunks", json=payload, headers=headers).json()["count"] == 1
    assert client.post("/api/v1/knowledge/chunks", json=payload, headers=headers).json()["count"] == 0
    modified = json.loads(json.dumps(payload))
    modified["chunks"][0]["text"] = "different resolution"
    assert client.post("/api/v1/knowledge/chunks", json=modified, headers=headers).status_code == 409
    repo = client.app.state.repository
    rows = repo.claim_queued_chunks("team-a")
    repo.finish_knowledge_chunks(rows, "failed")
    assert client.post("/api/v1/knowledge/retry").json()["requeued"] == 0
    assert client.post("/api/v1/knowledge/retry", headers=headers).json()["requeued"] == 1
    rows = repo.claim_queued_chunks("team-a")
    repo.finish_knowledge_chunks(
        [
            {
                **r,
                "embedding": [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
                "embedding_model": "text-embedding-3-small",
            }
            for r in rows
        ],
        "ready",
    )
    query = {"query": "database timeout", "metadata": {"environment": "production"}}
    matches = client.post("/api/v1/knowledge/search", json=query, headers=headers).json()
    assert len(matches) == 1 and matches[0]["section"] == "resolution"
    assert "embedding" not in matches[0]
    assert client.post("/api/v1/knowledge/search", json=query).json() == []
    query["metadata"]["environment"] = "staging"
    assert client.post("/api/v1/knowledge/search", json=query, headers=headers).json() == []


def test_historical_context_used_without_symptom(client, sample):
    incident_id = upload(client, sample)
    repo = client.app.state.repository
    repo.save_knowledge_chunks(
        [
            {
                "id": "case-history",
                "case_id": "previous-incident",
                "tenant_id": "demo-team",
                "section": "resolution",
                "ordinal": 0,
                "text": "db connection timeout resolved by rollback",
                "metadata": {},
                "embedding": None,
                "embedding_model": None,
                "index_status": "ready",
            }
        ]
    )
    response = client.post(
        f"/api/v1/incidents/{incident_id}/investigate", json={"run_id": str(uuid4()), "mode": "demo"}
    )
    assert response.status_code == 200
    assert response.json()["metrics"]["historical_matches"][0]["case_id"] == "previous-incident"


def test_tenant_identifier_validation_on_knowledge_routes(client):
    for path in ("/api/v1/knowledge/status", "/api/v1/incidents", "/api/v1/runs"):
        assert client.get(path, headers={"X-Tenant-ID": "invalid/tenant"}).status_code == 422
