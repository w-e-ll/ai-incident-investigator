"""Bounded, redacted canonical incident.v1 production input."""

import hashlib
import json
from datetime import UTC, datetime

from pydantic import ValidationError

from core.parser import MAX_BYTES, MAX_LINES, redact, redact_attributes
from core.schemas import Event, InvestigationError, Parsed, ParseIssue


def parse_bundle(data: bytes) -> Parsed:
    if len(data) > MAX_BYTES:
        raise InvestigationError("upload_too_large", "Maximum upload size is 2 MiB", 413)
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvestigationError("bundle_invalid", "Invalid UTF-8 incident.v1 JSON") from exc
    if not isinstance(payload, dict):
        raise InvestigationError("bundle_invalid", "Expected an incident.v1 JSON object")
    if payload.get("schema_version") != "incident.v1":
        raise InvestigationError("bundle_version", "Expected schema_version incident.v1")
    logs, changes = payload.get("events", []), payload.get("changes", [])
    if not isinstance(logs, list) or not isinstance(changes, list):
        raise InvestigationError("bundle_invalid", "events and changes must be arrays")
    records = logs + changes
    if not records:
        raise InvestigationError("bundle_empty", "incident.v1 bundle has no events")
    if len(records) > MAX_LINES:
        raise InvestigationError("too_many_events", "Maximum is 10,000 events", 413)
    events, issues = [], []
    warnings = {"Structured attributes are preserved in redacted event evidence."}
    digest = hashlib.sha256(data).hexdigest()[:12]
    rejected = 0
    for number, item in enumerate(records, 1):
        try:
            if not isinstance(item, dict):
                raise ValueError("Expected an event object")
            timestamp = item.get("timestamp")
            aware = None
            if timestamp is not None:
                if not isinstance(timestamp, str):
                    raise ValueError("timestamp must be an ISO-8601 string")
                aware = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if aware.tzinfo is None:
                    aware = None
                    warnings.add("Timestamps without timezone are excluded from the timeline.")
                else:
                    aware = aware.astimezone(UTC)
            kind = item.get("kind", "change" if number > len(logs) else "log")
            message = item.get("message") or item.get("operation") or f"{kind} event"
            if not isinstance(message, str) or not message.strip():
                raise ValueError("message or operation must be a string")
            attrs = item.get("attributes", {})
            if not isinstance(attrs, dict):
                raise ValueError("attributes must be an object")
            attrs = {**attrs, **{k: item[k] for k in ("duration_ms", "status") if k in item}}
            service = item.get("service") or payload.get("service") or "unknown"
            level = str(
                item.get("severity") or ("ERROR" if item.get("status") == "ERROR" else "INFO")
            ).upper()
            level = {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(level, level)
            if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"}:
                level = "UNKNOWN"
            events.append(
                Event(
                    id=f"E-{digest}-{number}",
                    line_start=number,
                    line_end=number,
                    timestamp=aware,
                    original_timestamp=timestamp,
                    kind=str(kind),
                    attributes=redact_attributes(attrs),
                    duration_ms=item.get("duration_ms"),
                    level=level,
                    service=redact(str(service)),
                    message=redact(
                        f"[{kind}] {message} | attributes={json.dumps(attrs, ensure_ascii=False)}"
                    ),
                    source=redact(json.dumps({"kind": kind, **item}, ensure_ascii=False)),
                    trace_id=redact(str(item["trace_id"])) if item.get("trace_id") else None,
                    request_id=redact(str(item["request_id"])) if item.get("request_id") else None,
                )
            )
        except (ValueError, TypeError, ValidationError):
            rejected += 1
            if len(issues) < 50:
                issues.append(ParseIssue(line=number, reason="Invalid event fields, timestamp, or length"))
    if not events:
        raise InvestigationError("bundle_empty", "No valid incident.v1 events")
    return Parsed(
        events=events,
        total_lines=len(records),
        rejected_records=rejected,
        issues=issues,
        warnings=sorted(warnings),
    )
