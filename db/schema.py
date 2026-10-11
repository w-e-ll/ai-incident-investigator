"""Typed identities and lifecycle columns; versioned domain snapshots in JSON."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
incidents = Table(
    "incidents",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(160), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("event_count", Integer, nullable=False),
    Column("parse_metadata", JSON, nullable=False),
    Column("tenant_id", String(100), nullable=False, default="demo-team", index=True),
)
events = Table(
    "events",
    metadata,
    Column("incident_id", String(36), ForeignKey("incidents.id"), primary_key=True),
    Column("id", String(80), primary_key=True),
    Column("payload", JSON, nullable=False),
)
runs = Table(
    "investigation_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("incident_id", String(36), ForeignKey("incidents.id"), nullable=False, index=True),
    Column("status", String(16), nullable=False),
    Column("mode", String(8), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("config", JSON, nullable=False),
    Column("payload", JSON),
    Column("error_code", String(80)),
)

knowledge_chunks = Table(
    "knowledge_chunks",
    metadata,
    Column("id", String(220), primary_key=True),
    Column("case_id", String(120), nullable=False, index=True),
    Column("tenant_id", String(100), nullable=False, index=True),
    Column("section", String(32), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("text", String(12000), nullable=False),
    Column("metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
    Column("embedding", JSON().with_variant(Vector(1536), "postgresql")),
    Column("embedding_model", String(100)),
    Column("index_status", String(20), nullable=False, default="queued"),
    Column("claimed_at", DateTime(timezone=True)),
)
