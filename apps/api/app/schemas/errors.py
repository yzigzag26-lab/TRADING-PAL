"""Stable error response contracts."""

from pydantic import BaseModel, ConfigDict


class ValidationIssue(BaseModel):
    """A validation issue without echoing potentially sensitive input values."""

    model_config = ConfigDict(extra="forbid")

    location: list[str | int]
    message: str
    code: str


class ErrorDetail(BaseModel):
    """Machine-readable and human-readable error details."""

    code: str
    message: str
    request_id: str
    details: list[ValidationIssue] | None = None


class ErrorResponse(BaseModel):
    """Common error envelope returned by the API."""

    error: ErrorDetail
