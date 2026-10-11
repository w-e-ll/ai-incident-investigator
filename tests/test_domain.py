import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.evidence import group_errors, select_evidence, validate_report
from core.investigator import Decision, Investigator, ToolRequest, demo_report, execute_tool
from core.parser import MAX_BYTES, parse, redact
from core.schemas import InvestigationError, Report, RunRequest
from core.settings import Settings
from tests.conftest import SAMPLES


def test_redaction_covers_structured_secrets():
    raw = 'password=hunter2 {"api_key":"sk-supersecret", "token":"private"} Bearer abc.xyz'
    redacted = redact(raw)
    assert all(secret not in redacted for secret in ["hunter2", "supersecret", "private", "abc.xyz"])
    assert "[REDACTED]" in redacted


def test_missing_timezone_is_not_assumed():
    parsed = parse(b'{"timestamp":"2026-10-06T12:00:00","message":"hello"}', "jsonl")
    assert parsed.events[0].timestamp is None
    assert "timezone" in " ".join(parsed.warnings)


def test_malformed_line_preserves_provenance():
    parsed = parse(b'not-json\n{"message":"failure","level":"ERROR"}\n', "jsonl")
    assert parsed.rejected_records == 1
    assert parsed.events[0].line_start == 2
    assert parsed.issues[0].line == 1


def test_multiline_text():
    parsed = parse((SAMPLES / "sample.log").read_bytes(), "text")
    assert len(parsed.events) == 3
    assert parsed.events[1].line_end == 5
    assert "pool exhausted" in parsed.events[1].message


@pytest.mark.parametrize(
    "data,code",
    [(b"", "no_events"), (b"\xff", "encoding"), (b"a" * (MAX_BYTES + 1), "upload_too_large")],
    ids=["empty", "non-utf8", "oversized"],
)
def test_invalid_inputs(data, code):
    with pytest.raises(InvestigationError) as error:
        parse(data, "jsonl")
    assert error.value.code == code


def test_groups_separate_services_and_severities(sample):
    parsed = parse(sample, "jsonl")
    groups = group_errors(parsed.events)
    assert len(groups) == 2
    assert {g.count for g in groups} == {12}
    assert sum(g.count for g in groups) == 24
    assert any(e.level == "INFO" for e in select_evidence(parsed.events, groups))


def test_citation_validator_rejects_invented_quote(sample):
    events = parse(sample, "jsonl").events
    report = demo_report(events, group_errors(events))
    report.facts[0].evidence[0].quote = "fabricated observation"
    with pytest.raises(InvestigationError, match="quote"):
        validate_report(report, events, {e.id for e in events})


def test_citation_validator_requires_seen_evidence(sample):
    events = parse(sample, "jsonl").events
    report = demo_report(events, group_errors(events))
    with pytest.raises(InvestigationError, match="unavailable"):
        validate_report(report, events, set())


def test_probable_cause_requires_strong_hypothesis(sample):
    events = parse(sample, "jsonl").events
    payload = demo_report(events, group_errors(events)).model_dump()
    payload.update(conclusion="probable_cause", probable_cause_id="H1")
    with pytest.raises(ValidationError):
        Report.model_validate(payload)


@pytest.mark.parametrize(
    "name", ["db_timeout.jsonl", "config_change.jsonl", "independent_failures.jsonl", "insufficient.jsonl"]
)
def test_demo_abstains_and_has_missing_evidence(name):
    events = parse((SAMPLES / name).read_bytes(), "jsonl").events
    runner = Investigator(Settings(_env_file=None), RunRequest(run_id=uuid4()), events, group_errors(events))
    report, metrics = runner.run()
    assert report.conclusion != "probable_cause"
    assert report.missing_evidence
    assert metrics.evidence_validated and metrics.llm_calls == 0 and metrics.cost_usd == "0"


class FakeModel:
    def __init__(self, decisions, usage=True):
        self.decisions = iter(decisions)
        self.usage = usage

    def invoke(self, messages):
        assert "untrusted" in messages[0].content
        return {
            "parsed": next(self.decisions),
            "parsing_error": None,
            "raw": SimpleNamespace(
                usage_metadata={"input_tokens": 100, "output_tokens": 200} if self.usage else None
            ),
        }


def test_live_graph_tools_then_valid_report(sample):
    events = parse(sample, "jsonl").events
    groups = group_errors(events)
    report = demo_report(events, groups)
    for hypothesis in report.hypotheses:
        hypothesis.supporting_evidence_ids = hypothesis.supporting_evidence_ids[:1]
    model = FakeModel(
        [
            Decision(
                action="tool", tool=ToolRequest(name="get_trace", query="checkout-1", end=None), report=None
            ),
            Decision(action="report", tool=None, report=report),
        ]
    )
    settings = Settings(
        _env_file=None,
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("2"),
        price_as_of="2026-10-06",
    )
    progress = []
    runner = Investigator(
        settings,
        RunRequest(run_id=uuid4(), mode="live"),
        events,
        groups,
        model=model,
        on_progress=progress.append,
    )
    _, metrics = runner.run()
    assert metrics.llm_calls == 2
    assert metrics.tool_calls[0].matched == 2
    assert metrics.cost_usd == "0.00100000"
    assert "get_trace" in metrics.steps
    assert progress == metrics.execution
    assert [item.status for item in progress if item.stage == "model"] == [
        "started",
        "completed",
        "started",
        "completed",
    ]
    tool_result = next(item for item in progress if item.stage == "tool" and item.status == "completed")
    assert len(tool_result.evidence_ids) == 2
    assert (
        next(item for item in progress if item.stage == "tool" and item.status == "started").detail
        == "Query: checkout-1"
    )


def test_final_call_cannot_request_another_tool(sample):
    events = parse(sample, "jsonl").events
    model = FakeModel(
        [
            Decision(
                action="tool", tool=ToolRequest(name="search_events", query="timeout", end=None), report=None
            )
        ]
    )
    runner = Investigator(
        Settings(_env_file=None),
        RunRequest(run_id=uuid4(), mode="live", max_calls=1),
        events,
        group_errors(events),
        model=model,
    )
    with pytest.raises(InvestigationError) as error:
        runner.run()
    assert error.value.code == "call_budget"
    assert runner.metrics().llm_calls == 1


def test_unknown_usage_does_not_become_zero_cost(sample):
    events = parse(sample, "jsonl").events
    report = demo_report(events, group_errors(events))
    for hypothesis in report.hypotheses:
        hypothesis.supporting_evidence_ids = hypothesis.supporting_evidence_ids[:1]
    model = FakeModel([Decision(action="report", tool=None, report=report)], usage=False)
    runner = Investigator(
        Settings(_env_file=None, input_usd_per_million=1, output_usd_per_million=2, price_as_of="2026-10-06"),
        RunRequest(run_id=uuid4(), mode="live"),
        events,
        group_errors(events),
        model=model,
    )
    _, metrics = runner.run()
    assert metrics.cost_usd is None


def test_tool_window_rejects_naive_time(sample):
    events = parse(sample, "jsonl").events
    with pytest.raises(InvestigationError):
        execute_tool(
            ToolRequest(name="get_time_window", query="2026-10-06T12:00:00", end="2026-10-06T12:01:00Z"),
            events,
            group_errors(events),
        )


def test_sensitive_values_not_persisted_as_source():
    payload = json.dumps({"message": "Failed password=abc", "token": "sensitivevalue"}).encode()
    event = parse(payload, "jsonl").events[0]
    assert "sensitivevalue" not in event.source and "abc" not in event.message


def test_provider_authentication_error_does_not_echo_key(sample):
    import httpx
    from openai import AuthenticationError

    class RejectedModel:
        def invoke(self, messages):
            response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com"))
            raise AuthenticationError("Invalid API key: sk-never-echo-this", response=response, body=None)

    events = parse(sample, "jsonl").events
    runner = Investigator(
        Settings(_env_file=None),
        RunRequest(run_id=uuid4(), mode="live"),
        events,
        group_errors(events),
        model=RejectedModel(),
    )
    with pytest.raises(InvestigationError) as caught:
        runner.run()
    assert caught.value.code == "provider_authentication"
    assert "sk-never-echo-this" not in str(caught.value)
    assert runner.metrics().llm_calls == 1
    assert runner.metrics().usage[0].input_tokens is None
    assert not any(item.stage == "demo" for item in runner.execution)
