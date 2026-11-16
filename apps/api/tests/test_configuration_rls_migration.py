"""Regression tests for the configuration-table RLS migration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "apps/api/alembic/versions/20261116_0004_configuration_rls.py"


def test_configuration_rls_migration_targets_both_private_tables() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20261116_0004"' in source
    assert 'down_revision = "20261115_0003"' in source
    for table in ("app_settings", "risk_settings"):
        assert f"ALTER TABLE baymax.{table} ENABLE ROW LEVEL SECURITY" in source
        for action in ("select", "insert", "update"):
            assert f"{table}_app_{action}" in source


def test_configuration_policies_match_runtime_privilege_group() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert source.count("TO baymax_app") == 6
    assert source.count("USING (true)") == 4
    assert source.count("WITH CHECK (true)") == 4
    assert "FOR DELETE" not in source
    assert "TO baymax_runtime" not in source


def test_migration_does_not_force_rls_or_change_table_grants() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "FORCE ROW LEVEL SECURITY" not in source
    assert "GRANT " not in source
    assert "REVOKE " not in source


def test_downgrade_removes_only_new_policies_and_disables_rls() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "DROP POLICY IF EXISTS" in source
    assert "DISABLE ROW LEVEL SECURITY" in source
    assert "DROP TABLE" not in source
