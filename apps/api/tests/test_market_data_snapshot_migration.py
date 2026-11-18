"""Regression tests for append-only market-data provenance migration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "apps/api/alembic/versions/20261118_0005_market_data_snapshots.py"


def test_provenance_migration_creates_private_rls_protected_table() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20261118_0005"' in source
    assert 'down_revision = "20261116_0004"' in source
    assert "CREATE TABLE baymax.market_data_snapshots" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "TO baymax_app" in source
    assert "GRANT SELECT, INSERT" in source


def test_provenance_migration_does_not_grant_mutation_or_drop_history() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source
    assert "DROP TABLE" not in source
