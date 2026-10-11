"""Queue a resolved incident case for embedding/indexing."""

import argparse
import json
from pathlib import Path

import httpx

from core.knowledge import chunk_case


def build_payload(data: dict, tenant: str) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("case_id"), str) or not data["case_id"].strip():
        raise ValueError("Resolved case requires a non-empty case_id")
    for key in ("symptoms", "root_cause", "resolution", "verification"):
        value = data.get(key)
        if value is not None and not (
            isinstance(value, str) or isinstance(value, list) and all(isinstance(v, str) for v in value)
        ):
            raise ValueError(f"{key} must be a string or list of strings")
    sections = {
        key: data[key] if isinstance(data[key], str) else " ".join(map(str, data[key]))
        for key in ("symptoms", "root_cause", "resolution", "verification")
        if data.get(key)
    }
    metadata = dict(data.get("metadata", {}))
    for key in ("service", "environment", "title"):
        if data.get(key):
            metadata[key] = data[key]
    chunks = chunk_case(data["case_id"], tenant, sections, metadata)
    if not chunks:
        raise ValueError("Resolved case requires at least one non-empty section")
    return {
        "tenant_id": tenant,
        "chunks": [
            {
                "id": c.chunk_id,
                "case_id": c.case_id,
                "section": c.section,
                "ordinal": c.ordinal,
                "text": c.text,
                "metadata": c.metadata,
            }
            for c in chunks
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant")
    args = parser.parse_args()
    data = json.loads(args.case.read_text(encoding="utf-8"))
    tenant = args.tenant or data.get("tenant_id", "demo-team")
    body = build_payload(data, tenant)
    from core.schemas import KnowledgeChunkBatch

    body = KnowledgeChunkBatch.model_validate(body).model_dump(mode="json")
    response = httpx.post(
        f"{args.api}/api/v1/knowledge/chunks", json=body, headers={"X-Tenant-ID": tenant}, timeout=30
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
