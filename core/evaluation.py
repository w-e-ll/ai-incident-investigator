"""Observable deterministic checks, not a claim of semantic correctness."""

import re

from core.evidence import validate_report
from core.schemas import Event, Report

INJECTION = re.compile(
    r"ignore (all |previous |prior )?instructions|system prompt|reveal.*(secret|key)|act as", re.I
)


def input_checks(events: list[Event], history: list[dict]) -> list[dict[str, str]]:
    suspect = sum(bool(INJECTION.search(e.message)) for e in events)
    suspect += sum(bool(INJECTION.search(str(row.get("text", "")))) for row in history)
    return [
        {
            "check": "input_contract",
            "status": "pass",
            "detail": f"{len(events)} normalized events passed schema validation.",
        },
        {
            "check": "prompt_injection_markers",
            "status": "warning" if suspect else "pass",
            "detail": f"{suspect} instruction-like records; logs and history remain untrusted data. Keyword checks are incomplete.",
        },
        {
            "check": "historical_context",
            "status": "pass",
            "detail": f"{len(history)} historical sections supplied as comparative context, excluded from current fact citations.",
        },
    ]


def output_checks(report: Report, events: list[Event], seen: set[str]) -> list[dict[str, str]]:
    validate_report(report, events, seen)
    return [
        {
            "check": "report_contract",
            "status": "pass",
            "detail": "Facts, hypotheses, missing evidence and cause-selection invariants validated.",
        },
        {
            "check": "citation_integrity",
            "status": "pass",
            "detail": "Cited IDs were seen and quotes match current event messages.",
        },
        {
            "check": "semantic_correctness",
            "status": "unverified",
            "detail": "Citation checks do not establish causality. Compare the report with engineering ground truth.",
        },
    ]
