"""Initial incident, event, and investigation lifecycle schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False),
        sa.Column("parse_metadata", sa.JSON, nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), primary_key=True),
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("payload", sa.JSON, nullable=False),
    )
    op.create_table(
        "investigation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("payload", sa.JSON),
        sa.Column("error_code", sa.String(80)),
    )
    op.create_index("ix_investigation_runs_incident_id", "investigation_runs", ["incident_id"])
    op.create_index("ix_investigation_runs_created_at", "investigation_runs", ["created_at"])


def downgrade():
    op.drop_table("investigation_runs")
    op.drop_table("events")
    op.drop_table("incidents")
