"""Single-owner password login and session lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    LoginRateLimiter,
    create_session_token,
    verify_owner_password,
    verify_session_token,
)
from app.core.config import Settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    authenticated: bool


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _require_trusted_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin is None or origin not in settings.cors_allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed.")


def _client_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


@router.post("/login", response_model=SessionResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> SessionResponse:
    """Verify the one owner password and issue a secure browser session cookie."""
    settings = _settings(request)
    _require_trusted_origin(request, settings)
    if not settings.owner_password_hash or not settings.session_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this deployment.",
        )

    limiter = request.app.state.login_limiter
    if not isinstance(limiter, LoginRateLimiter):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    client_key = _client_key(request)
    if limiter.is_limited(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many unsuccessful attempts. Try again later.",
            headers={"Retry-After": "900"},
        )

    if not verify_owner_password(payload.password, settings.owner_password_hash):
        limiter.record_failure(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The password is incorrect.",
        )

    limiter.clear(client_key)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(settings.session_secret),
        max_age=SESSION_TTL_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return SessionResponse(authenticated=True)


@router.get("/session", response_model=SessionResponse)
async def read_session(request: Request) -> SessionResponse:
    """Return whether the request carries a valid owner session."""
    settings = _settings(request)
    authenticated = verify_session_token(
        request.cookies.get(SESSION_COOKIE_NAME),
        settings.session_secret,
    )
    return SessionResponse(authenticated=authenticated)


@router.post("/logout", response_model=SessionResponse)
async def logout(request: Request, response: Response) -> SessionResponse:
    """Clear the browser's owner session cookie."""
    _require_trusted_origin(request, _settings(request))
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return SessionResponse(authenticated=False)
