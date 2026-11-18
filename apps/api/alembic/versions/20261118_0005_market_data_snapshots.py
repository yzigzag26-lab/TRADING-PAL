"""Create append-only market-data provenance snapshots.

Revision ID: 20261118_0005
Revises: 20261116_0004
Create Date: 2026-11-18
"""

from __future__ import annotations

from alembic import op

revision = "20261118_0005"
down_revision = "20261116_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the private append-only market-data provenance table."""
    op.execute(
        """
        CREATE TABLE baymax.market_data_snapshots (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          exchange text NOT NULL,
          market text NOT NULL,
          symbol text NOT NULL,
          data_type text NOT NULL,
          interval text,
          source text NOT NULL,
          market_event_timestamp timestamptz,
          exchange_event_timestamp timestamptz,
          received_timestamp timestamptz,
          validated_timestamp timestamptz NOT NULL,
          age_ms_at_validation integer,
          connection_state text NOT NULL,
          validation_state text NOT NULL,
          requested_start timestamptz,
          requested_end timestamptz,
          is_complete boolean,
          request_id uuid,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_market_data_snapshots_data_type
            CHECK (data_type IN ('trade_price', 'historical_ohlcv')),
          CONSTRAINT ck_market_data_snapshots_validation_state
            CHECK (validation_state IN ('VALIDATED', 'INCOMPLETE')),
          CONSTRAINT ck_market_data_snapshots_age_nonnegative
            CHECK (age_ms_at_validation IS NULL OR age_ms_at_validation >= 0),
          CONSTRAINT ck_market_data_snapshots_payload_object
            CHECK (jsonb_typeof(payload) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_market_data_snapshots_symbol_created
        ON baymax.market_data_snapshots (symbol, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_market_data_snapshots_type_created
        ON baymax.market_data_snapshots (data_type, created_at DESC)
        """
    )
    op.execute("ALTER TABLE baymax.market_data_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY market_data_snapshots_app_select
        ON baymax.market_data_snapshots
        FOR SELECT TO baymax_app USING (true)
        """
    )
    op.execute(
        """
        CREATE POLICY market_data_snapshots_app_insert
        ON baymax.market_data_snapshots
        FOR INSERT TO baymax_app WITH CHECK (true)
        """
    )
    op.execute(
        "REVOKE ALL ON TABLE baymax.market_data_snapshots "
        "FROM PUBLIC, anon, authenticated, service_role"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE baymax.market_data_snapshots TO baymax_app"
    )


def downgrade() -> None:
    """Retain provenance history; never drop persisted market-data evidence."""
    raise RuntimeError(
        "Market-data provenance is append-only; this migration cannot be downgraded."
    )
