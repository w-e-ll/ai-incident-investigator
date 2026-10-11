"""Verify progress reaches a socket client while model work is still blocked."""

import json
import socket
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import uvicorn

import core.service
from api.main import create_app
from core.evidence import group_errors
from core.investigator import Decision, Investigator, demo_report
from core.parser import parse
from core.settings import Settings


def test_model_started_arrives_before_model_response(monkeypatch, repository, sample):
    events = parse(sample, "jsonl").events
    report = demo_report(events, group_errors(events))
    for hypothesis in report.hypotheses:
        hypothesis.supporting_evidence_ids = hypothesis.supporting_evidence_ids[:1]
    release = threading.Event()

    class DelayedModel:
        def invoke(self, messages):
            if not release.wait(timeout=10):
                raise RuntimeError("Client never received progress before model completion")
            return {
                "parsed": Decision(
                    action="report",
                    tool=None,
                    report=report,
                    decision_summary="The sample supports a dependency failure hypothesis.",
                ),
                "parsing_error": None,
                "raw": SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 100}),
            }

    def runner(*args, **kwargs):
        return Investigator(*args, **kwargs, model=DelayedModel())

    monkeypatch.setattr(core.service, "Investigator", runner)
    app = create_app(Settings(_env_file=None, openai_api_key="test-only"), repository)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        worker.start()
        deadline = time.monotonic() + 10
        try:
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
                incident = client.post(
                    "/api/v1/incidents", files={"file": ("synthetic.jsonl", sample)}
                ).json()
                updates = []
                with client.stream(
                    "POST",
                    f"/api/v1/incidents/{incident['incident_id']}/investigate/stream",
                    json={"run_id": str(uuid4()), "mode": "live", "max_calls": 1},
                ) as response:
                    for line in response.iter_lines():
                        update = json.loads(line)
                        updates.append(update)
                        if (
                            update["type"] == "progress"
                            and update["event"]["stage"] == "model"
                            and update["event"]["status"] == "started"
                        ):
                            assert not release.is_set()
                            release.set()
                assert updates[-1]["type"] == "result"
                assert updates[-1]["result"]["metrics"]["llm_calls"] == 1
        finally:
            release.set()
            server.should_exit = True
            worker.join(timeout=10)
