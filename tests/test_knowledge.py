from core.hybrid_search import vector_literal
from core.incident_bundle import parse_bundle
from core.knowledge import chunk_case, metadata_allowed, rrf_fuse


def test_chunks_keep_sections_and_overlap():
    chunks = chunk_case("case-1", "tenant-a", {"root_cause": "word " * 500}, {"environment": "prod"})
    assert len(chunks) == 2
    assert all(c.section == "root_cause" and c.tenant_id == "tenant-a" for c in chunks)
    assert chunks[0].text.split()[-45:] == chunks[1].text.split()[:45]


def test_rrf_prefers_overlap_between_rankings():
    result = rrf_fuse(["shared", "a", "b"], ["x", "shared", "a"], limit=3)
    assert result[0][0] == "shared"


def test_metadata_filter_is_exact_and_tenant_scoped():
    assert metadata_allowed(
        {"tenant_id": "a", "environment": "prod", "tags": ["db"]}, {"tenant_id": "a", "tags": "db"}
    )
    assert not metadata_allowed({"tenant_id": "b", "environment": "prod"}, {"tenant_id": "a"})


def test_vector_literal_requires_1536_dimensions():
    assert vector_literal([0.0] * 1536).startswith("[")
    import pytest

    with pytest.raises(ValueError):
        vector_literal([0.0])


def test_incident_v1_bundle_normalizes_events():
    payload = {
        "schema_version": "incident.v1",
        "service": "checkout",
        "events": [
            {
                "timestamp": "2026-10-07T12:00:00Z",
                "kind": "span",
                "operation": "checkout.create",
                "service": "checkout",
                "status": "ERROR",
                "trace_id": "t1",
                "attributes": {"http.status_code": 504},
            }
        ],
        "changes": [],
    }
    parsed = parse_bundle(__import__("json").dumps(payload).encode())
    assert parsed.events[0].trace_id == "t1"
    assert "http.status_code" in parsed.events[0].message


def test_queue_case_builds_section_aware_payload():
    from scripts.queue_case import build_payload

    payload = build_payload(
        {
            "case_id": "case-1",
            "root_cause": "pool exhausted",
            "resolution": ["rollback"],
            "metadata": {"environment": "production"},
        },
        "tenant-a",
    )
    assert payload["tenant_id"] == "tenant-a"
    assert payload["chunks"][0]["section"] == "root_cause"


def test_structured_bundle_redacts_secrets_and_handles_bad_fields():
    import json

    payload = {
        "schema_version": "incident.v1",
        "events": [
            {
                "timestamp": "2026-10-08T12:00:00",
                "message": "password=private",
                "attributes": {"api_key": "sk-should-not-survive"},
            },
            "invalid-record",
        ],
    }
    parsed = parse_bundle(json.dumps(payload).encode())
    assert parsed.events[0].timestamp is None
    assert parsed.rejected_records == 1
    assert "private" not in parsed.events[0].message
    assert "sk-should-not-survive" not in parsed.events[0].source


def test_structured_bundle_rejects_wrong_envelopes_and_size():
    import pytest

    from core.parser import MAX_BYTES
    from core.schemas import InvestigationError

    for raw in (b"[]", b'{"schema_version":"incident.v1","events":{}}', b"x" * (MAX_BYTES + 1)):
        with pytest.raises(InvestigationError):
            parse_bundle(raw)
