"""Validated runtime configuration for the Baymax API."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "https://baymax-nu.vercel.app",
)
VALID_ENVIRONMENTS = frozenset({"development", "test", "production"})


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings loaded from the process environment."""

    app_env: str
    log_level: str
    cors_allowed_origins: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> Settings:
        """Load and validate environment variables without reading secret files."""
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env not in VALID_ENVIRONMENTS:
            allowed = ", ".join(sorted(VALID_ENVIRONMENTS))
            raise ValueError(f"APP_ENV must be one of: {allowed}")

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if not isinstance(getattr(logging, log_level, None), int):
            raise ValueError("LOG_LEVEL must be a valid Python logging level")

        raw_origins = os.getenv(
            "CORS_ALLOWED_ORIGINS",
            ",".join(DEFAULT_CORS_ORIGINS),
        )
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in raw_origins.split(",")
            if origin.strip()
        )
        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin")
        if "*" in origins:
            raise ValueError("Wildcard CORS origins are not allowed")

        return cls(
            app_env=app_env,
            log_level=log_level,
            cors_allowed_origins=origins,
        )
