"""Align existing databases with tenant isolation and native retrieval types."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "incidents", sa.Column("tenant_id", sa.String(100), nullable=False, server_default="demo-team")
    )
    op.create_index("ix_incidents_tenant_id", "incidents", ["tenant_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN metadata TYPE jsonb USING metadata::jsonb")


def downgrade():
    op.drop_index("ix_incidents_tenant_id", table_name="incidents")
    op.drop_column("incidents", "tenant_id")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN metadata TYPE json USING metadata::json")
