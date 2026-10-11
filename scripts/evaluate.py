"""Offline regression dataset evaluation; never contacts a model."""

import json
from pathlib import Path
from uuid import uuid4

from core.evidence import group_errors
from core.investigator import Investigator
from core.parser import parse
from core.schemas import RunRequest
from core.settings import Settings


def main():
    results = []
    for filename in (
        "db_timeout.jsonl",
        "config_change.jsonl",
        "independent_failures.jsonl",
        "insufficient.jsonl",
    ):
        parsed = parse((Path("samples") / filename).read_bytes(), "jsonl")
        report, metrics = Investigator(
            Settings(_env_file=None, openai_api_key=""),
            RunRequest(run_id=uuid4(), mode="demo"),
            parsed.events,
            group_errors(parsed.events),
        ).run()
        results.append(
            {
                "sample": filename,
                "mode": "demo",
                "conclusion": report.conclusion,
                "evaluation": metrics.evaluation,
            }
        )
    Path("var").mkdir(exist_ok=True)
    Path("var/evaluation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Evaluated four fixtures without model calls. Results: var/evaluation.json")


if __name__ == "__main__":
    main()
