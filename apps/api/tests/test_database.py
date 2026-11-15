from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.pool import QueuePool

from app.db.session import create_database_engine, normalize_database_url


def test_normalizes_postgres_scheme_to_psycopg_three_and_requires_ssl() -> None:
    value = "postgresql://baymax_runtime:secret@db.example.supabase.co:5432/postgres"
    normalized = normalize_database_url(value)
    url = make_url(normalized)

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "baymax_runtime"
    assert url.password == "secret"
    assert url.query["sslmode"] == "require"


def test_preserves_explicit_ssl_mode() -> None:
    normalized = normalize_database_url(
        "postgresql+psycopg://baymax_runtime:secret@db.example:5432/postgres?sslmode=verify-full"
    )
    assert make_url(normalized).query["sslmode"] == "verify-full"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "sqlite:///not-allowed.db",
        "postgresql://",
        "postgresql://user@/database",
    ],
)
def test_rejects_invalid_runtime_database_urls(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_database_url(value)


def test_creates_bounded_pre_ping_engine_without_opening_a_connection() -> None:
    engine = create_database_engine(
        "postgresql://baymax_runtime:secret@db.example.supabase.co:5432/postgres"
    )
    try:
        pool = cast(QueuePool, engine.pool)
        assert pool._pre_ping is True
        assert pool.size() == 5
    finally:
        engine.dispose()
