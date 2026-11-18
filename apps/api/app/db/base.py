"""SQLAlchemy declarative base for Baymax database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for models stored in the private baymax schema."""

    pass

