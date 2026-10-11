"""Add tenant-safe historical knowledge chunks and pgvector indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(220), primary_key=True),
        sa.Column("case_id", sa.String(120), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("section", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.String(12000), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("embedding", sa.JSON),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("index_status", sa.String(20), nullable=False, server_default="queued"),
    )
    op.create_index("ix_knowledge_chunks_tenant_id", "knowledge_chunks", ["tenant_id"])
    op.create_index("ix_knowledge_chunks_case_id", "knowledge_chunks", ["case_id"])
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536) USING NULL")
        op.execute(
            "CREATE INDEX ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX ix_knowledge_chunks_text_search ON knowledge_chunks USING gin (to_tsvector('english', text))"
        )


def downgrade():
    op.drop_table("knowledge_chunks")
