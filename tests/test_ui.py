import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

import ui.client


def test_ui_sample_to_report_without_real_network(monkeypatch, client):
    def adapter(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ui.client.APIProblem(response.json()["message"])
        return response.json()

    monkeypatch.setattr(ui.client, "call", adapter)

    def streamed(incident_id, body):
        response = client.post(f"/api/v1/incidents/{incident_id}/investigate/stream", json=body)
        for line in response.text.splitlines():
            yield json.loads(line)

    monkeypatch.setattr(ui.client, "investigation_updates", streamed)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=20)
    app.run()
    assert not app.exception
    next(b for b in app.button if b.label == "Load sample").click().run()
    assert not app.exception
    assert app.metric[0].value == "29"
    assert next(b for b in app.button if b.label == "Investigate").disabled
    assert any("API key" in item.value for item in app.error)
    app.selectbox(key="investigation_mode").set_value("demo").run()
    next(b for b in app.button if b.label == "Investigate").click().run()
    assert not app.exception
    assert app.session_state["result"]["mode"] == "demo"
    assert app.session_state["result"]["metrics"]["execution"]
    assert any(m.value == "0" for m in app.metric)
    app.radio[0].set_value("History & monitoring").run()
    assert not app.exception
    assert any(m.value == "1" for m in app.metric)


def test_ui_tenant_upload_history_and_knowledge(monkeypatch, client):
    def adapter(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ui.client.APIProblem(response.json().get("message", "API failed"))
        return response.json()

    def streamed(incident_id, body):
        response = client.post(
            f"/api/v1/incidents/{incident_id}/investigate/stream",
            json=body,
            headers={"X-Tenant-ID": body["tenant_id"]},
        )
        yield from (json.loads(line) for line in response.text.splitlines())

    monkeypatch.setattr(ui.client, "call", adapter)
    monkeypatch.setattr(ui.client, "investigation_updates", streamed)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=20)
    app.run()
    app.text_input(key="tenant_id").set_value("team-a").run()
    next(b for b in app.button if b.label == "Load sample").click().run()
    assert not app.exception
    assert client.get("/api/v1/incidents").json() == []
    assert len(client.get("/api/v1/incidents", headers={"X-Tenant-ID": "team-a"}).json()) == 1
    app.selectbox(key="investigation_mode").set_value("demo").run()
    next(b for b in app.button if b.label == "Investigate").click().run()
    assert not app.exception and app.session_state["result"]["mode"] == "demo"
    app.radio[0].set_value("Knowledge base").run()
    assert not app.exception
    next(c for c in app.checkbox if c.label == "Use the reviewed synthetic resolved case").check().run()
    next(b for b in app.button if b.label == "Save case to indexing queue").click().run()
    assert not app.exception
    assert (
        client.get("/api/v1/knowledge/status", headers={"X-Tenant-ID": "team-a"}).json()["counts"]["queued"]
        == 4
    )
    app.text_input(key="tenant_id").set_value("team-b").run()
    assert app.session_state["result"] is None


def test_background_submission_immediately_shows_status_button(monkeypatch, client):
    def adapter(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ui.client.APIProblem(response.json().get("message", "API failed"))
        return response.json()

    monkeypatch.setattr(ui.client, "call", adapter)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=20)
    app.run()
    next(b for b in app.button if b.label == "Load sample").click().run()
    app.selectbox(key="investigation_mode").set_value("demo").run()
    next(c for c in app.checkbox if c.label == "Run as a durable background job").check()
    next(b for b in app.button if b.label == "Investigate").click().run()
    assert not app.exception
    assert any(b.label == "Check pending job or interrupted run" for b in app.button)
    assert len(client.get("/api/v1/runs").json()) == 1
    next(b for b in app.button if b.label == "Check pending job or interrupted run").click().run()
    assert len(client.get("/api/v1/runs").json()) == 1

    refreshed = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "streamlit_app.py"), default_timeout=20
    )
    refreshed.query_params.update(dict(app.query_params))
    refreshed.run()
    assert not refreshed.exception
    assert refreshed.session_state["pending"]["run_id"] == app.session_state["pending"]["run_id"]
    assert refreshed.metric[0].value == "29"

    # The older saved-result control must also treat queued/started as normal.
    next(b for b in app.button if b.label == "Check saved result before a new run").click().run()
    assert not app.exception
    assert not any("Run failed" in item.value or "run_incomplete" in item.value for item in app.error)
    from uuid import UUID

    from core.schemas import RunRequest

    repo = client.app.state.repository
    row = repo.queued_runs()[0]
    repo.claim(UUID(row["incident_id"]), RunRequest.model_validate(row["config"]), from_queue=True)
    next(b for b in app.button if b.label == "Check saved result before a new run").click().run()
    assert not app.exception
    assert not any("Run failed" in item.value or "run_incomplete" in item.value for item in app.error)
    assert any("Run status: started" in item.value for item in app.info)
    assert len(client.get("/api/v1/runs").json()) == 1


def test_refresh_restores_saved_report_without_upload_or_new_run(monkeypatch, client):
    def adapter(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ui.client.APIProblem(response.json().get("message", "API failed"))
        return response.json()

    monkeypatch.setattr(ui.client, "call", adapter)

    def streamed(incident_id, body):
        response = client.post(f"/api/v1/incidents/{incident_id}/investigate/stream", json=body)
        yield from (json.loads(line) for line in response.text.splitlines())

    monkeypatch.setattr(ui.client, "investigation_updates", streamed)
    script = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    original = AppTest.from_file(script, default_timeout=20).run()
    next(b for b in original.button if b.label == "Load sample").click().run()
    original.selectbox(key="investigation_mode").set_value("demo").run()
    next(b for b in original.button if b.label == "Investigate").click().run()
    result = original.session_state["result"]
    refreshed = AppTest.from_file(script, default_timeout=20)
    refreshed.query_params.update(dict(original.query_params))
    refreshed.run()
    assert not refreshed.exception
    assert refreshed.session_state["result"]["run_id"] == result["run_id"]
    assert refreshed.metric[0].value == "29"
    assert len(client.get("/api/v1/runs").json()) == 1

    # A different tenant cannot restore the report from another tenant's URL.
    isolated = AppTest.from_file(script, default_timeout=20)
    isolated.query_params.update(dict(original.query_params))
    isolated.query_params["tenant_id"] = "other-team"
    isolated.run()
    assert not isolated.exception
    assert isolated.session_state["result"] is None
    assert isolated.session_state["incident"] is None
