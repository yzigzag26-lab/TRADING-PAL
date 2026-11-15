"""Tests for the Gate 1 audit-log metadata."""

from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base
from app.db.models import AuditLog


def test_audit_log_is_in_private_schema() -> None:
    assert AuditLog.__table__.schema == "baymax"
    assert Base.metadata.tables["baymax.audit_logs"] is AuditLog.__table__


def test_audit_log_has_required_integrity_constraints() -> None:
    constraint_names = {
        constraint.name for constraint in AuditLog.__table__.constraints
    }
    assert {
        "ck_audit_logs_event_type_nonempty",
        "ck_audit_logs_actor_type",
        "ck_audit_logs_resource_pair",
        "ck_audit_logs_metadata_object",
    }.issubset(constraint_names)


def test_audit_log_uses_jsonb_and_timezone_aware_timestamps() -> None:
    assert isinstance(AuditLog.__table__.columns["metadata"].type, JSONB)
    assert AuditLog.__table__.columns["occurred_at"].type.timezone is True
