"""SQLAlchemy declarative base for Baymax database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for models stored in the private baymax schema."""

    pass


# Register model metadata before Alembic autogeneration.
from app.db.models import AuditLog as _AuditLog  # noqa: F401
