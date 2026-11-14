"""Health endpoint response schema."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Liveness response; deliberately does not expose dependency internals."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["baymax-api"]
    version: str
