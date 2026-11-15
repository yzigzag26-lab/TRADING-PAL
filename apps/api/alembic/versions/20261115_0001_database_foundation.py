"""Create the private Baymax database foundation.

Revision ID: 20261115_0001
Revises:
Create Date: 2026-11-15
"""

from __future__ import annotations

from alembic import op

revision = "20261115_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create private schema and non-login privilege-group roles."""
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'baymax_app') THEN
            CREATE ROLE baymax_app
              NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'baymax_migrator') THEN
            CREATE ROLE baymax_migrator
              NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
          END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE SCHEMA IF NOT EXISTS baymax AUTHORIZATION postgres
        """
    )
    op.execute(
        """
        COMMENT ON SCHEMA baymax IS
          'Private application schema for Baymax. Not exposed through the Supabase Data API.'
        """
    )
    op.execute("REVOKE ALL ON SCHEMA baymax FROM PUBLIC")
    op.execute("REVOKE ALL ON SCHEMA baymax FROM anon, authenticated, service_role")
    op.execute("GRANT USAGE ON SCHEMA baymax TO baymax_app")
    op.execute("GRANT USAGE, CREATE ON SCHEMA baymax TO baymax_migrator")
    op.execute("ALTER ROLE baymax_app SET search_path = pg_catalog, baymax")
    op.execute("ALTER ROLE baymax_migrator SET search_path = pg_catalog, baymax")


def downgrade() -> None:
    """Revoke application access without dropping schema or potentially valuable data."""
    op.execute("REVOKE ALL ON SCHEMA baymax FROM baymax_app")
    op.execute("REVOKE ALL ON SCHEMA baymax FROM baymax_migrator")
    op.execute("ALTER ROLE baymax_app RESET search_path")
    op.execute("ALTER ROLE baymax_migrator RESET search_path")
