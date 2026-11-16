"""Enable least-privilege RLS policies for singleton configuration tables.

Revision ID: 20261116_0004
Revises: 20261115_0003
Create Date: 2026-11-16
"""

from __future__ import annotations

from alembic import op

revision = "20261116_0004"
down_revision = "20261115_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Require the Baymax application privilege group for settings table access."""
    op.execute("ALTER TABLE baymax.app_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE baymax.risk_settings ENABLE ROW LEVEL SECURITY")

    for table in ("app_settings", "risk_settings"):
        op.execute(
            f"""
            CREATE POLICY {table}_app_select
            ON baymax.{table}
            FOR SELECT
            TO baymax_app
            USING (true)
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_app_insert
            ON baymax.{table}
            FOR INSERT
            TO baymax_app
            WITH CHECK (true)
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_app_update
            ON baymax.{table}
            FOR UPDATE
            TO baymax_app
            USING (true)
            WITH CHECK (true)
            """
        )


def downgrade() -> None:
    """Remove only the policies introduced here and restore the prior RLS state."""
    for table in ("app_settings", "risk_settings"):
        for action in ("select", "insert", "update"):
            op.execute(
                f"DROP POLICY IF EXISTS {table}_app_{action} ON baymax.{table}"
            )
        op.execute(f"ALTER TABLE baymax.{table} DISABLE ROW LEVEL SECURITY")
