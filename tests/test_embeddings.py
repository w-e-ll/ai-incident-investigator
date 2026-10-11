import pytest

from core.embeddings import EMBEDDING_DIMENSIONS, embed_chunks


def test_embedding_batch_marks_chunks_ready():
    chunks = [{"id": "c1", "text": "database pool exhausted", "index_status": "embedding"}]
    result = embed_chunks(chunks, lambda texts: [[0.0] * EMBEDDING_DIMENSIONS for _ in texts])
    assert result[0]["index_status"] == "ready"
    assert result[0]["embedding_model"] == "text-embedding-3-small"


def test_embedding_rejects_mismatched_provider_result():
    with pytest.raises(ValueError, match="mismatched"):
        embed_chunks([{"id": "c1", "text": "x"}], lambda _: [])
