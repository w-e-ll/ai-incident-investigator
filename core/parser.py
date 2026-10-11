"""Bounded parsers with redacted provenance; missing timezone is never guessed."""

import hashlib
import json
import re
from datetime import UTC, datetime

from pydantic import ValidationError

from core.schemas import Event, InvestigationError, Parsed, ParseIssue

MAX_BYTES = 2 * 1024 * 1024
MAX_LINES = 10000
TEXT = re.compile(
    r"^(?P<timestamp>\S+)\s+(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)"
    r"\s+(?P<service>[\w.-]+)\s+(?P<message>.*)$"
)
SECRET = re.compile(
    r"(?i)\b(password|passwd|token|api[_-]?key|secret|authorization|cookie)"
    r"([\"']?\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def redact(text: str) -> str:
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    return SECRET.sub(lambda m: f"{m[1]}{m[2]}[REDACTED]", text)


def redact_attributes(value):
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]"
            if re.search(r"password|passwd|token|secret|api.?key|authorization|cookie", str(k), re.I)
            else redact_attributes(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_attributes(v) for v in value]
    return redact(value) if isinstance(value, str) else value


def parse(data: bytes, format_name: str) -> Parsed:
    if len(data) > MAX_BYTES:
        raise InvestigationError("upload_too_large", "Maximum upload size is 2 MiB", 413)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvestigationError("encoding", "Upload a UTF-8 file") from exc
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise InvestigationError("too_many_lines", "Maximum is 10,000 physical lines", 413)
    events: list[Event] = []
    issues: list[ParseIssue] = []
    rejected = 0
    warnings: set[str] = set()
    digest = hashlib.sha256(data).hexdigest()[:12]
    for number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            if len(raw) > 16000:
                raise ValueError("Record exceeds 16,000 characters")
            if format_name == "jsonl":
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("Expected a JSON object")
                message = obj.get("message")
                if not isinstance(message, str) or not message.strip():
                    raise ValueError("message must be a non-empty string")
                fields = obj
            elif format_name == "text":
                match = TEXT.match(raw)
                if match is None:
                    if events and raw[:1].isspace() and events[-1].line_end == number - 1:
                        previous = events[-1]
                        combined = previous.message + "\n" + redact(raw)
                        source = previous.source + "\n" + redact(raw)
                        if len(combined) > 12000 or len(source) > 16000:
                            raise ValueError("Multiline event exceeds length limit")
                        events[-1] = previous.model_copy(
                            update={
                                "message": combined,
                                "source": source,
                                "line_end": number,
                            }
                        )
                        continue
                    raise ValueError("Expected timestamp LEVEL service message")
                fields = match.groupdict()
                message = fields["message"]
                if not message.strip():
                    raise ValueError("message must not be empty")
            else:
                raise ValueError("Unsupported format")
            stamp = fields.get("timestamp")
            timestamp = None
            if stamp is not None:
                if not isinstance(stamp, str):
                    raise ValueError("timestamp must be an ISO-8601 string")
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    warnings.add("Timestamps without timezone are excluded from the timeline.")
                else:
                    timestamp = parsed.astimezone(UTC)
            else:
                warnings.add("Some events have no timestamp and are excluded from the timeline.")
            level = str(fields.get("level", "UNKNOWN")).upper()
            level = {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(level, level)
            if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"}:
                level = "UNKNOWN"
            service = fields.get("service", "unknown")
            if not isinstance(service, str):
                raise ValueError("service must be a string")
            events.append(
                Event(
                    id=f"E-{digest}-{number}",
                    line_start=number,
                    line_end=number,
                    timestamp=timestamp,
                    original_timestamp=stamp,
                    kind=fields.get("kind", "log"),
                    attributes=redact_attributes(fields.get("attributes", {})),
                    duration_ms=fields.get("duration_ms"),
                    level=level,
                    service=redact(service),
                    message=redact(message),
                    source=redact(raw),
                    trace_id=redact(fields["trace_id"]) if isinstance(fields.get("trace_id"), str) else None,
                    request_id=redact(fields["request_id"])
                    if isinstance(fields.get("request_id"), str)
                    else None,
                )
            )
        except (ValueError, TypeError, ValidationError):
            rejected += 1
            if len(issues) < 50:
                issues.append(ParseIssue(line=number, reason="Invalid record or field length/type"))
    if not events:
        raise InvestigationError("no_events", "No supported events found; use a sample format")
    warnings.add("Redaction is best-effort. Review sensitive data before any live investigation.")
    return Parsed(
        events=events,
        total_lines=len(lines),
        rejected_records=rejected,
        issues=issues,
        warnings=sorted(warnings),
    )
