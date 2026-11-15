"""Tests for the Gate 1 audit-log metadata."""

from typing import cast

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.db.models import AuditLog


def test_audit_log_is_in_private_schema() -> None:
    assert AuditLog.__table__.schema == "baymax"
    assert Base.metadata.tables["baymax.audit_logs"] is AuditLog.__table__


def test_audit_log_has_required_integrity_constraints() -> None:
    table = cast(Table, AuditLog.__table__)
    constraint_names = {constraint.name for constraint in table.constraints}
    assert {
        "ck_audit_logs_event_type_nonempty",
        "ck_audit_logs_actor_type",
        "ck_audit_logs_resource_pair",
        "ck_audit_logs_metadata_object",
    }.issubset(constraint_names)


def test_audit_log_uses_jsonb_and_timezone_aware_timestamps() -> None:
    table = cast(Table, AuditLog.__table__)
    assert isinstance(table.columns["metadata"].type, JSONB)
    occurred_at_type = cast(DateTime, table.columns["occurred_at"].type)
    assert occurred_at_type.timezone is True
