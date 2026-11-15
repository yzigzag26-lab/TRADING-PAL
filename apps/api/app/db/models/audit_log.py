"""Append-only audit log model."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """An immutable record of a Baymax system or owner action."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(event_type)) > 0",
            name="ck_audit_logs_event_type_nonempty",
        ),
        CheckConstraint(
            "actor_type in ('owner', 'system', 'service')",
            name="ck_audit_logs_actor_type",
        ),
        CheckConstraint(
            "(resource_type is null and resource_id is null) "
            "or (resource_type is not null and length(btrim(resource_type)) > 0)",
            name="ck_audit_logs_resource_pair",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="ck_audit_logs_metadata_object",
        ),
        Index("ix_audit_logs_occurred_at", text("occurred_at DESC")),
        Index(
            "ix_audit_logs_event_type_occurred_at",
            "event_type",
            text("occurred_at DESC"),
        ),
        Index(
            "ix_audit_logs_resource",
            "resource_type",
            "resource_id",
            postgresql_where=text("resource_type IS NOT NULL"),
        ),
        {"schema": "baymax"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'system'"),
    )
    actor_id: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
