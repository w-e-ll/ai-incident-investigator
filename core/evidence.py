"""Deterministic grouping, bounded evidence selection, and citation verification."""

import hashlib
import json
import re

import tiktoken

from core.schemas import ErrorGroup, Event, InvestigationError, Report


def fingerprint(message: str) -> str:
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<uuid>", message.lower())
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<ip>", text)
    text = re.sub(r"\b\d{4,}\b", "<number>", text)
    return re.sub(r"\s+", " ", text).strip()[:500]


def group_errors(events: list[Event]) -> list[ErrorGroup]:
    buckets: dict[tuple[str, str, str], list[Event]] = {}
    for event in events:
        if event.level not in {"ERROR", "CRITICAL"}:
            continue
        key = event.service, event.level, fingerprint(event.message)
        buckets.setdefault(key, []).append(event)
    groups = []
    for (service, level, signature), values in buckets.items():
        times = [v.timestamp for v in values if v.timestamp]
        group_id = hashlib.sha256(f"{service}|{level}|{signature}".encode()).hexdigest()[:12]
        groups.append(
            ErrorGroup(
                id=f"G-{group_id}",
                service=service,
                level=level,
                fingerprint=signature,
                count=len(values),
                first_seen=min(times) if times else None,
                last_seen=max(times) if times else None,
                evidence_ids=[v.id for v in values],
            )
        )
    return sorted(groups, key=lambda g: (-g.count, g.id))


def select_evidence(events: list[Event], groups: list[ErrorGroup], limit: int = 60) -> list[Event]:
    by_id = {event.id: event for event in events}
    selected: dict[str, Event] = {}
    # Round-robin representatives prevent one noisy group from taking the entire pack.
    for offset in (0, -1):
        for group in groups[:20]:
            event = by_id[group.evidence_ids[offset]]
            selected[event.id] = event
    markers = [e for e in events if re.search(r"deploy|release|config|restart", e.message, re.I)]
    for event in markers[:8]:
        selected.setdefault(event.id, event)
    positions = {e.id: i for i, e in enumerate(events)}
    for event in list(selected.values()):
        position = positions[event.id]
        for neighbor in events[max(0, position - 1) : position + 2]:
            if len(selected) < limit:
                selected.setdefault(neighbor.id, neighbor)
    for event in events[:5] + events[-5:]:
        if len(selected) < limit:
            selected.setdefault(event.id, event)
    return sorted(selected.values(), key=lambda e: e.line_start)[:limit]


def token_count(text: str) -> int:
    return len(tiktoken.get_encoding("cl100k_base").encode(text, disallowed_special=()))


def pack_event(event: Event) -> dict:
    return {
        "id": event.id,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "level": event.level,
        "service": event.service,
        "message": event.message[:600],
        "trace_id": event.trace_id,
        "kind": event.kind,
        "attributes": event.attributes,
        "duration_ms": event.duration_ms,
        "line": event.line_start,
    }


def serialize_pack(events: list[Event], groups: list[ErrorGroup], selected: list[Event]) -> str:
    return json.dumps(
        {
            "total_events": len(events),
            "error_events": sum(g.count for g in groups),
            "total_error_groups": len(groups),
            "groups": [g.model_dump(mode="json", exclude={"evidence_ids"}) for g in groups[:20]],
            "events": [pack_event(e) for e in selected],
            "selection": "Bounded sample. Missing events are not evidence of absence.",
        },
        ensure_ascii=False,
    )


def validate_report(report: Report, events: list[Event], seen_ids: set[str]) -> None:
    by_id = {e.id: e for e in events}
    for fact in report.facts:
        for citation in fact.evidence:
            if citation.event_id not in seen_ids or citation.event_id not in by_id:
                raise InvestigationError("invalid_evidence", "Report cites unavailable evidence", 502)
            if citation.quote not in by_id[citation.event_id].message:
                raise InvestigationError("invalid_quote", "Report quote does not match evidence", 502)
    for hypothesis in report.hypotheses:
        references = hypothesis.supporting_evidence_ids + hypothesis.contradicting_evidence_ids
        if any(ref not in seen_ids or ref not in by_id for ref in references):
            raise InvestigationError("invalid_evidence", "Hypothesis cites unavailable evidence", 502)
        if set(hypothesis.supporting_evidence_ids) & set(hypothesis.contradicting_evidence_ids):
            raise InvestigationError("conflicting_evidence", "Evidence assigned conflicting roles", 502)
