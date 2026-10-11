"""Generate small deterministic synthetic datasets; contains no real customer data."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "samples"
ROOT.mkdir(exist_ok=True)
START = datetime(2026, 10, 6, 12, tzinfo=UTC)


def row(second, service, level, message, trace_id=None):
    return {
        "timestamp": (START + timedelta(seconds=second)).isoformat(),
        "service": service,
        "level": level,
        "message": message,
        "trace_id": trace_id,
    }


def save(name, rows):
    (ROOT / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


save(
    "db_timeout.jsonl",
    [
        row(0, "checkout", "INFO", "Request completed status=200", "healthy-1"),
        row(5, "checkout", "INFO", "Deployment v2.4 completed; connection pool limit unchanged"),
        row(8, "database", "WARNING", "Active connections reached configured limit=20"),
        *[
            event
            for i in range(12)
            for event in [
                row(10 + i * 2, "checkout", "ERROR", "DB connection timeout after 3000ms", f"checkout-{i}"),
                row(11 + i * 2, "gateway", "ERROR", "Upstream checkout returned status=502", f"checkout-{i}"),
            ]
        ],
        row(40, "database", "INFO", "Connections returned below limit after traffic decreased"),
        row(43, "checkout", "INFO", "Request completed status=200", "healthy-2"),
    ],
)
save(
    "config_change.jsonl",
    [
        row(0, "payments", "INFO", "Payment authorization successful", "before-1"),
        row(5, "payments", "INFO", "Config reload: credential_version changed from v4 to v5"),
        row(6, "payments", "WARNING", "Loaded credential_version=v5; provider expects v4"),
        *[
            row(10 + i, "payments", "ERROR", "Authentication failed: credential version mismatch", f"pay-{i}")
            for i in range(8)
        ],
        row(25, "payments", "INFO", "Config rollback: credential_version=v4"),
        row(26, "payments", "INFO", "Payment authorization successful", "after-1"),
    ],
)
save(
    "independent_failures.jsonl",
    [
        row(0, "checkout", "INFO", "Health check successful"),
        *[
            event
            for i in range(6)
            for event in [
                row(10 + i, "checkout", "ERROR", "DB connection timeout after 3000ms", f"db-{i}"),
                row(10 + i, "media", "ERROR", "Disk quota exceeded on image volume", f"media-{i}"),
            ]
        ],
        row(30, "gateway", "INFO", "Media and checkout use independent storage and database dependencies"),
    ],
)
save(
    "insufficient.jsonl",
    [
        {
            "level": "ERROR",
            "service": "gateway",
            "message": "Request failed status=502",
            "trace_id": "partial-1",
        },
        row(20, "gateway", "INFO", "Log collector resumed; earlier upstream events unavailable"),
    ],
)
(ROOT / "sample.log").write_text(
    "2026-10-06T12:00:00Z INFO checkout Request completed status=200\n"
    "2026-10-06T12:00:10Z ERROR checkout DB connection timeout\n"
    "    Traceback (most recent call last):\n"
    '    File "db_client.py", line 42, in acquire\n'
    "    TimeoutError: connection pool exhausted\n"
    "2026-10-06T12:00:11Z ERROR gateway Upstream checkout returned status=502\n",
    encoding="utf-8",
)
