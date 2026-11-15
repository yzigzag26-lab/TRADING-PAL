"""Add append-only audit log foundation.

Revision ID: 20261115_0002
Revises: 20261115_0001
Create Date: 2026-11-15
"""

from __future__ import annotations

from alembic import op

revision = "20261115_0002"
down_revision = "20261115_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the audit log table and its query indexes."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS baymax.audit_logs (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          event_type text NOT NULL,
          actor_type text NOT NULL DEFAULT 'system',
          actor_id text,
          resource_type varchar(100),
          resource_id varchar(255),
          request_id uuid,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          occurred_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_audit_logs_event_type_nonempty
            CHECK (length(btrim(event_type)) > 0),
          CONSTRAINT ck_audit_logs_actor_type
            CHECK (actor_type IN ('owner', 'system', 'service')),
          CONSTRAINT ck_audit_logs_resource_pair
            CHECK (
              (resource_type IS NULL AND resource_id IS NULL)
              OR (resource_type IS NOT NULL AND length(btrim(resource_type)) > 0)
            ),
          CONSTRAINT ck_audit_logs_metadata_object
            CHECK (jsonb_typeof(metadata) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_occurred_at
          ON baymax.audit_logs (occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type_occurred_at
          ON baymax.audit_logs (event_type, occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_logs_resource
          ON baymax.audit_logs (resource_type, resource_id)
          WHERE resource_type IS NOT NULL
        """
    )
    op.execute(
        "REVOKE ALL ON TABLE baymax.audit_logs FROM PUBLIC, anon, authenticated, service_role"
    )
    op.execute("GRANT SELECT, INSERT ON TABLE baymax.audit_logs TO baymax_app")


def downgrade() -> None:
    """Keep audit history; destructive audit-log downgrades are intentionally unsupported."""
    # Audit history is retained permanently. Do not drop this table in a downgrade.
    pass
