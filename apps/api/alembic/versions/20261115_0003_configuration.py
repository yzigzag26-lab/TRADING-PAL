"""Add singleton application and risk settings.

Revision ID: 20261115_0003
Revises: 20261115_0002
Create Date: 2026-11-15
"""

from __future__ import annotations

from alembic import op

revision = "20261115_0003"
down_revision = "20261115_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create private configuration tables with conservative unset risk limits."""
    op.execute(
        """
        CREATE TABLE baymax.app_settings (
          id smallint PRIMARY KEY DEFAULT 1,
          timezone varchar(64) NOT NULL DEFAULT 'UTC',
          default_currency varchar(12),
          default_exchange varchar(32) NOT NULL DEFAULT 'BINANCE',
          general_settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_app_settings_singleton CHECK (id = 1),
          CONSTRAINT ck_app_settings_timezone_nonempty
            CHECK (length(btrim(timezone)) > 0),
          CONSTRAINT ck_app_settings_currency_format
            CHECK (default_currency IS NULL OR default_currency ~ '^[A-Z0-9]{2,12}$'),
          CONSTRAINT ck_app_settings_exchange_nonempty
            CHECK (length(btrim(default_exchange)) > 0),
          CONSTRAINT ck_app_settings_general_object
            CHECK (jsonb_typeof(general_settings) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE baymax.risk_settings (
          id smallint PRIMARY KEY DEFAULT 1,
          max_risk_per_trade_value numeric(20, 8),
          max_risk_per_trade_unit varchar(20),
          max_daily_loss_value numeric(20, 8),
          max_daily_loss_unit varchar(20),
          max_open_positions integer,
          max_leverage numeric(10, 4),
          default_risk_currency varchar(12),
          additional_settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_risk_settings_singleton CHECK (id = 1),
          CONSTRAINT ck_risk_settings_trade_risk_pair CHECK (
            (max_risk_per_trade_value IS NULL AND max_risk_per_trade_unit IS NULL)
            OR (max_risk_per_trade_value IS NOT NULL AND max_risk_per_trade_unit IS NOT NULL)
          ),
          CONSTRAINT ck_risk_settings_trade_risk_range CHECK (
            max_risk_per_trade_value IS NULL OR (
              max_risk_per_trade_value > 0 AND (
                (max_risk_per_trade_unit = 'percent' AND max_risk_per_trade_value <= 100)
                OR max_risk_per_trade_unit = 'quote_currency'
              )
            )
          ),
          CONSTRAINT ck_risk_settings_trade_risk_unit CHECK (
            max_risk_per_trade_unit IS NULL
            OR max_risk_per_trade_unit IN ('percent', 'quote_currency')
          ),
          CONSTRAINT ck_risk_settings_daily_loss_pair CHECK (
            (max_daily_loss_value IS NULL AND max_daily_loss_unit IS NULL)
            OR (max_daily_loss_value IS NOT NULL AND max_daily_loss_unit IS NOT NULL)
          ),
          CONSTRAINT ck_risk_settings_daily_loss_range CHECK (
            max_daily_loss_value IS NULL OR (
              max_daily_loss_value > 0 AND (
                (max_daily_loss_unit = 'percent' AND max_daily_loss_value <= 100)
                OR max_daily_loss_unit = 'quote_currency'
              )
            )
          ),
          CONSTRAINT ck_risk_settings_daily_loss_unit CHECK (
            max_daily_loss_unit IS NULL
            OR max_daily_loss_unit IN ('percent', 'quote_currency')
          ),
          CONSTRAINT ck_risk_settings_open_positions CHECK (
            max_open_positions IS NULL OR max_open_positions >= 1
          ),
          CONSTRAINT ck_risk_settings_leverage CHECK (
            max_leverage IS NULL OR max_leverage >= 1
          ),
          CONSTRAINT ck_risk_settings_currency_nonempty CHECK (
            default_risk_currency IS NULL OR length(btrim(default_risk_currency)) > 0
          ),
          CONSTRAINT ck_risk_settings_additional_object CHECK (
            jsonb_typeof(additional_settings) = 'object'
          )
        )
        """
    )
    op.execute(
        """
        INSERT INTO baymax.app_settings (id, timezone, default_exchange)
        VALUES (1, 'UTC', 'BINANCE')
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO baymax.risk_settings (id)
        VALUES (1)
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        REVOKE ALL ON TABLE baymax.app_settings, baymax.risk_settings
        FROM PUBLIC, anon, authenticated, service_role
        """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE ON TABLE baymax.app_settings, baymax.risk_settings
        TO baymax_app
        """
    )


def downgrade() -> None:
    """Remove configuration tables only when both remain empty of owner data."""
    op.execute("DROP TABLE IF EXISTS baymax.risk_settings")
    op.execute("DROP TABLE IF EXISTS baymax.app_settings")
