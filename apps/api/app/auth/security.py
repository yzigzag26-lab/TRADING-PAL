"""Password verification and signed single-owner browser sessions."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "__Host-baymax_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5

_password_hasher = PasswordHasher()


class LoginRateLimiter:
    """Small single-instance limiter for the one-owner login endpoint."""

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def is_limited(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        attempts = self._failures[key]
        while attempts and current - attempts[0] >= LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            self._failures.pop(key, None)
            return False
        return len(attempts) >= LOGIN_MAX_FAILURES

    def record_failure(self, key: str, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        attempts = self._failures[key]
        while attempts and current - attempts[0] >= LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(current)

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)


def verify_owner_password(password: str, password_hash: str) -> bool:
    """Verify a supplied password against the configured Argon2id hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_session_token(secret: str) -> str:
    """Create a signed, timestamped, non-identifying owner session token."""
    serializer = URLSafeTimedSerializer(secret, salt="baymax-owner-session-v1")
    return serializer.dumps({"sub": "owner", "sid": secrets.token_urlsafe(18), "v": 1})


def verify_session_token(token: str | None, secret: str | None) -> bool:
    """Validate signature, age, version, and the single-owner subject claim."""
    if not token or not secret:
        return False
    serializer = URLSafeTimedSerializer(secret, salt="baymax-owner-session-v1")
    try:
        payload: Any = serializer.loads(token, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("sub") == "owner"
        and payload.get("v") == 1
        and isinstance(payload.get("sid"), str)
    )
