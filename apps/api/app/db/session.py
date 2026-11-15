"""Runtime SQLAlchemy engine and request-scoped sessions."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import HTTPException, Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def normalize_database_url(value: str) -> str:
    """Validate a PostgreSQL URL and select the psycopg 3 SQLAlchemy dialect."""
    raw = value.strip()
    if not raw:
        raise ValueError("DATABASE_URL must not be empty")

    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw.removeprefix("postgres://")

    url = make_url(raw)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use PostgreSQL with the psycopg 3 driver")

    if not url.host or not url.username or not url.database:
        raise ValueError("DATABASE_URL must include a host, username, and database")

    query = dict(url.query)
    query.setdefault("sslmode", "require")
    return url.set(query=query).render_as_string(hide_password=False)


def create_database_engine(database_url: str) -> Engine:
    """Create a bounded, health-checked SQLAlchemy engine for the runtime role."""
    normalized_url = normalize_database_url(database_url)
    return create_engine(
        normalized_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
        pool_recycle=1800,
        pool_timeout=15,
    )


def verify_database_connection(engine: Engine) -> None:
    """Verify PostgreSQL connectivity without exposing connection details."""
    with engine.connect() as connection:
        current_user: str = connection.execute(text("SELECT current_user")).scalar_one()
        if current_user != "baymax_runtime":
            raise RuntimeError("DATABASE_URL must authenticate as the dedicated baymax_runtime role")
        result: int = connection.execute(text("SELECT 1")).scalar_one()
        if result != 1:
            raise RuntimeError("Database connectivity verification returned an unexpected result")


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Yield a request-scoped database session from the runtime engine."""
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="Database access is not configured.",
        )

    with factory() as session:
        yield session
