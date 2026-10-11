"""Track indexing claims for explicit stale recovery."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_chunks", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    # Preexisting in-flight work has unknown billing; require explicit retry.
    op.execute("UPDATE knowledge_chunks SET index_status = 'failed' WHERE index_status = 'embedding'")


def downgrade():
    op.drop_column("knowledge_chunks", "claimed_at")
