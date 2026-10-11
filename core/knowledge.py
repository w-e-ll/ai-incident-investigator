"""Deterministic knowledge chunks and hybrid retrieval primitives."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    case_id: str
    tenant_id: str
    section: str
    ordinal: int
    text: str
    metadata: dict[str, Any]


def chunk_section(
    case_id: str,
    tenant_id: str,
    section: str,
    text: str,
    max_words: int = 330,
    overlap_words: int = 45,
    metadata: dict[str, Any] | None = None,
) -> list[KnowledgeChunk]:
    """Split a knowledge section without mixing root cause, resolution, or verification."""
    words = text.split()
    if not words:
        return []
    if max_words < 50 or overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("Invalid chunk limits")
    step = max_words - overlap_words
    result = []
    for ordinal, start in enumerate(range(0, len(words), step)):
        part = " ".join(words[start : start + max_words]).strip()
        if not part:
            break
        result.append(
            KnowledgeChunk(
                f"{case_id}:{section}:{ordinal}", case_id, tenant_id, section, ordinal, part, metadata or {}
            )
        )
        if start + max_words >= len(words):
            break
    return result


def chunk_case(
    case_id: str, tenant_id: str, sections: dict[str, str], metadata: dict[str, Any] | None = None
) -> list[KnowledgeChunk]:
    allowed = {"symptoms", "root_cause", "resolution", "verification"}
    unknown = set(sections) - allowed
    if unknown:
        raise ValueError(f"Unsupported knowledge sections: {sorted(unknown)}")
    return [
        chunk
        for section, text in sections.items()
        for chunk in chunk_section(case_id, tenant_id, section, text, metadata=metadata)
    ]


def rrf_fuse(
    lexical_ids: list[str], vector_ids: list[str], limit: int = 5, k: int = 60
) -> list[tuple[str, float]]:
    """Fuse two ranked lists; scores are explainable and independent of raw distance scales."""
    if limit < 1 or k < 1:
        raise ValueError("limit and k must be positive")
    scores: dict[str, float] = {}
    for ranking in (lexical_ids, vector_ids):
        for rank, item_id in enumerate(ranking, 1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]


def metadata_allowed(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Exact, tenant-safe prefilter. Lists support membership; scalars use equality."""
    for key, expected in filters.items():
        actual = metadata.get(key)
        if isinstance(actual, list):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True
