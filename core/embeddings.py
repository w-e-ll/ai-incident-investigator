"""Bounded embedding worker primitives; provider calls are explicit and never retried blindly."""

import math
from collections.abc import Callable
from typing import Any

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def embed_chunks(
    chunks: list[dict[str, Any]],
    embed: Callable[[list[str]], list[list[float]]],
    model: str = EMBEDDING_MODEL,
) -> list[dict[str, Any]]:
    if not chunks:
        return []
    texts = [str(chunk["text"]).strip() for chunk in chunks]
    if any(not text for text in texts):
        raise ValueError("Embedding input cannot be empty")
    vectors = embed(texts)
    if len(vectors) != len(chunks):
        raise ValueError("Embedding provider returned a mismatched batch")
    result = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        if len(vector) != EMBEDDING_DIMENSIONS or not all(math.isfinite(float(v)) for v in vector):
            raise ValueError("Unexpected embedding dimensions")
        result.append({**chunk, "embedding": vector, "embedding_model": model, "index_status": "ready"})
    return result


def openai_embedder(api_key: str, model: str = EMBEDDING_MODEL):
    from openai import OpenAI

    client = OpenAI(api_key=api_key, max_retries=0, timeout=30)

    def embed(texts: list[str]) -> list[list[float]]:
        response = client.embeddings.create(model=model, input=texts, dimensions=EMBEDDING_DIMENSIONS)
        return [item.embedding for item in response.data]

    return embed
