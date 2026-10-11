"""Strict contracts shared by parsers, investigator, persistence, and HTTP."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(Contract):
    id: str
    kind: str = Field(default="log", max_length=40)
    attributes: dict[str, JsonValue] = Field(default_factory=dict, max_length=128)
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    timestamp: AwareDatetime | None = None
    original_timestamp: str | None = None
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"]
    service: str = Field(max_length=100)
    message: str = Field(max_length=12000)
    source: str = Field(max_length=16000)
    trace_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)


class ParseIssue(Contract):
    line: int
    reason: str


class Parsed(Contract):
    events: list[Event]
    total_lines: int
    rejected_records: int
    issues: list[ParseIssue]
    warnings: list[str]


class ErrorGroup(Contract):
    id: str
    service: str
    level: str
    fingerprint: str
    count: int = Field(ge=1)
    first_seen: AwareDatetime | None
    last_seen: AwareDatetime | None
    evidence_ids: list[str]


class Evidence(Contract):
    event_id: str
    quote: str = Field(min_length=1, max_length=400)


class Fact(Contract):
    statement: str = Field(min_length=1, max_length=1200)
    evidence: list[Evidence] = Field(min_length=1, max_length=10)


class Hypothesis(Contract):
    id: str
    explanation: str = Field(min_length=1, max_length=2000)
    support: Literal["weak", "moderate", "strong"]
    rationale: str = Field(min_length=1, max_length=1500)
    supporting_evidence_ids: list[str] = Field(min_length=1, max_length=20)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    alternatives: list[str] = Field(min_length=1, max_length=5)


class MissingEvidence(Contract):
    hypothesis_id: str | None
    needed: str = Field(min_length=1, max_length=1200)
    next_check: str = Field(min_length=1, max_length=1200)


class Report(Contract):
    conclusion: Literal["insufficient_evidence", "competing_hypotheses", "probable_cause"]
    summary: str = Field(min_length=1, max_length=2000)
    probable_cause_id: str | None = None
    facts: list[Fact] = Field(min_length=1, max_length=20)
    hypotheses: list[Hypothesis] = Field(max_length=5)
    missing_evidence: list[MissingEvidence] = Field(min_length=1, max_length=15)
    limitations: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def check_links(self):
        ids = [h.id for h in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("Hypothesis IDs must be unique")
        if any(m.hypothesis_id and m.hypothesis_id not in ids for m in self.missing_evidence):
            raise ValueError("Unknown hypothesis reference")
        if self.conclusion == "probable_cause":
            candidate = next((h for h in self.hypotheses if h.id == self.probable_cause_id), None)
            if candidate is None or candidate.support != "strong":
                raise ValueError("Probable cause requires a strongly supported hypothesis")
        elif self.probable_cause_id is not None:
            raise ValueError("Only probable_cause can select a cause")
        if self.conclusion == "competing_hypotheses" and len(ids) < 2:
            raise ValueError("Competing hypotheses requires at least two hypotheses")
        return self


class UploadResponse(Contract):
    incident_id: UUID
    name: str
    created_at: AwareDatetime
    parsed: Parsed
    groups: list[ErrorGroup]


class KnowledgeChunkInput(Contract):
    id: str = Field(min_length=1, max_length=115)
    case_id: str = Field(min_length=1, max_length=120)
    section: Literal["symptoms", "root_cause", "resolution", "verification"]
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=12000)
    metadata: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)


class KnowledgeChunkBatch(Contract):
    tenant_id: str = Field(default="demo-team", min_length=1, max_length=100)
    chunks: list[KnowledgeChunkInput] = Field(min_length=1, max_length=100)


class KnowledgeSearchRequest(Contract):
    query: str = Field(min_length=1, max_length=2000)
    metadata: dict[str, str] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=20)


class RunRequest(Contract):
    tenant_id: str = Field(
        default="demo-team", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    metadata: dict[str, str] = Field(default_factory=dict, max_length=20)
    run_id: UUID
    mode: Literal["demo", "live"] = "demo"
    symptom: str = Field(default="", max_length=1000)
    max_calls: int = Field(default=3, ge=1, le=4)
    max_tool_calls: int = Field(default=4, ge=0, le=6)
    max_input_tokens: int = Field(default=16000, ge=1000, le=32000)
    max_output_tokens: int = Field(default=2000, ge=500, le=3000)


class CallUsage(Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)


class ToolCall(Contract):
    name: str
    matched: int = Field(ge=0)
    returned_ids: list[str]


class ExecutionEvent(Contract):
    """Observable execution and short public summaries, never private model reasoning."""

    sequence: int = Field(ge=1)
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    stage: Literal["prepare", "model", "decision", "tool", "validate", "demo"]
    status: Literal["started", "completed"]
    title: str = Field(max_length=200)
    detail: str = Field(max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=60)


class RunMetrics(Contract):
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    llm_calls: int = Field(ge=0)
    tool_calls: list[ToolCall]
    usage: list[CallUsage]
    model: str | None
    cost_usd: str | None
    price_snapshot: dict[str, str] | None
    raw_log_tokens_estimate: int = Field(ge=0)
    evidence_pack_tokens_estimate: int = Field(ge=0)
    evidence_events: int = Field(ge=0)
    total_events: int = Field(ge=0)
    evidence_validated: bool
    steps: list[str]
    execution: list[ExecutionEvent] = Field(default_factory=list, max_length=60)
    evaluation: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    historical_matches: list[dict[str, str | float | None]] = Field(default_factory=list, max_length=10)


class RunResponse(Contract):
    run_id: UUID
    incident_id: UUID
    status: Literal["completed"] = "completed"
    mode: Literal["demo", "live"]
    created_at: AwareDatetime
    report: Report
    metrics: RunMetrics


class RunSummary(Contract):
    run_id: UUID
    incident_id: UUID
    status: Literal["queued", "started", "completed", "failed"]
    mode: Literal["demo", "live"]
    created_at: AwareDatetime
    duration_ms: float | None
    error_code: str | None


class IncidentSummary(Contract):
    incident_id: UUID
    name: str
    created_at: AwareDatetime
    event_count: int


class APIError(Contract):
    code: str
    message: str
    request_id: str


class InvestigationUpdate(Contract):
    type: Literal["progress", "result", "error"]
    event: ExecutionEvent | None = None
    result: RunResponse | None = None
    error: APIError | None = None

    @model_validator(mode="after")
    def check_payload(self):
        expected = {"progress": "event", "result": "result", "error": "error"}[self.type]
        for name in ("event", "result", "error"):
            if (getattr(self, name) is not None) != (name == expected):
                raise ValueError("Stream update must have exactly its corresponding payload")
        return self


class InvestigationError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
