from __future__ import annotations

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.auth.security import SESSION_COOKIE_NAME
from app.core.config import Settings
from app.main import create_app

ORIGIN = "https://baymax-nu.vercel.app"
PASSWORD = "correct-test-password"


def make_client(*, configured: bool = True) -> TestClient:
    password_hash = PasswordHasher().hash(PASSWORD) if configured else None
    settings = Settings(
        app_env="test",
        log_level="INFO",
        cors_allowed_origins=(ORIGIN,),
        owner_password_hash=password_hash,
        session_secret="test-session-secret-that-is-long-enough-123456789",
    )
    return TestClient(create_app(settings), base_url="https://testserver")


def test_login_issues_secure_httponly_host_cookie() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    cookie = response.headers["set-cookie"]
    assert SESSION_COOKIE_NAME in cookie
    assert "httponly" in cookie.lower()
    assert "secure" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert "domain=" not in cookie.lower()


def test_wrong_password_does_not_issue_a_session() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"password": "wrong-password"},
            headers={"Origin": ORIGIN},
        )
        session = client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert session.json() == {"authenticated": False}


def test_session_endpoint_recognizes_login_and_logout() -> None:
    with make_client() as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        session = client.get("/api/v1/auth/session")
        logout = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
        after_logout = client.get("/api/v1/auth/session")

    assert login.status_code == 200
    assert session.json() == {"authenticated": True}
    assert logout.status_code == 200
    assert after_logout.json() == {"authenticated": False}
    assert "max-age=0" in logout.headers["set-cookie"].lower()


def test_login_rejects_untrusted_browser_origin() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
            headers={"Origin": "https://untrusted.example"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_login_fails_closed_when_password_hash_is_not_configured() -> None:
    with make_client(configured=False) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


def test_tampered_session_cookie_is_rejected() -> None:
    with make_client() as client:
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-valid-signed-session")
        response = client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_login_rate_limiter_blocks_after_five_failed_attempts() -> None:
    with make_client() as client:
        failures = []
        for _ in range(5):
            failures.append(client.post(
                "/api/v1/auth/login",
                json={"password": "wrong-password"},
                headers={"Origin": ORIGIN},
            ))
        limited = client.post(
            "/api/v1/auth/login",
            json={"password": PASSWORD},
            headers={"Origin": ORIGIN},
        )

    assert len(failures) == 5
    assert failures[-1].status_code == 401
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "900"
    assert limited.json()["error"]["code"] == "too_many_requests"
