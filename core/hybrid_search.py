"""Bounded PostgreSQL full-text/vector retrieval with reciprocal rank fusion."""

import math

HYBRID_SQL = """
WITH eligible AS (
 SELECT id, case_id, tenant_id, section, ordinal, text, metadata, embedding
 FROM knowledge_chunks
 WHERE tenant_id = :tenant_id AND index_status = 'ready'
   AND metadata @> CAST(:metadata AS jsonb)
), lexical AS (
 SELECT id, row_number() OVER (ORDER BY ts_rank(to_tsvector('english', text),
   plainto_tsquery('english', :query)) DESC, id) AS rank
 FROM eligible WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :query)
 ORDER BY rank LIMIT 50
), semantic AS (
 SELECT id, row_number() OVER (ORDER BY embedding <=> CAST(:embedding AS vector), id) AS rank
 FROM eligible WHERE embedding IS NOT NULL
 ORDER BY rank LIMIT 50
), fused AS (
 SELECT id, SUM(1.0 / (60 + rank)) AS rrf_score
 FROM (SELECT * FROM lexical UNION ALL SELECT * FROM semantic) rankings GROUP BY id
)
SELECT e.id, e.case_id, e.tenant_id, e.section, e.ordinal, e.text, e.metadata, f.rrf_score
FROM fused f JOIN eligible e ON e.id = f.id
ORDER BY f.rrf_score DESC, e.id LIMIT :limit
"""


def vector_literal(values: list[float]) -> str:
    if len(values) != 1536 or not all(math.isfinite(float(v)) for v in values):
        raise ValueError("Expected 1536 finite embedding values")
    return "[" + ",".join(str(float(value)) for value in values) + "]"
