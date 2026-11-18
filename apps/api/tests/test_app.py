from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.clock_health import ClockHealthMonitor, ClockHealthSnapshot
from app.core.config import Settings
from app.main import create_app


def make_client(
    origins: tuple[str, ...] = ("http://localhost:3000",),
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    settings = Settings(
        app_env="test",
        log_level="INFO",
        cors_allowed_origins=origins,
    )
    return TestClient(
        create_app(settings),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_health_endpoint_returns_minimal_liveness_payload() -> None:
    with make_client() as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "baymax-api",
        "version": "0.1.0",
    }
    assert str(UUID(response.headers["x-request-id"])) == response.headers["x-request-id"]


def test_openapi_contains_only_the_implemented_versioned_endpoint() -> None:
    with make_client() as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"]["title"] == "Baymax API"
    assert set(document["paths"]) == {
        "/api/v1/health",
        "/api/v1/analysis/prepare",
        "/api/v1/analysis/respond",
        "/api/v1/analysis/history",
        "/api/v1/auth/login",
        "/api/v1/auth/session",
        "/api/v1/auth/logout",
        "/api/v1/diagnostics/gate-3",
        "/api/v1/diagnostics/gate-3/durable-snapshot",
        "/api/v1/diagnostics/gate-3/websocket-rotation",
    }


def test_swagger_ui_is_enabled_and_redoc_remains_disabled() -> None:
    with make_client() as client:
        swagger = client.get("/docs")
        redoc = client.get("/redoc")

    assert swagger.status_code == 200
    assert "swagger-ui" in swagger.text.lower()
    assert "/openapi.json" in swagger.text
    assert redoc.status_code == 404


def test_cors_allows_the_configured_frontend_origin() -> None:
    with make_client() as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_does_not_allow_an_unconfigured_origin() -> None:
    with make_client() as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://unapproved.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "access-control-allow-origin" not in response.headers


def test_unhandled_errors_return_generic_message_without_exception_details() -> None:
    application = create_app(
        Settings(
            app_env="test",
            log_level="INFO",
            cors_allowed_origins=("http://localhost:3000",),
        )
    )

    @application.get("/test-unhandled-error")
    async def raise_error() -> None:
        raise RuntimeError("sensitive internal detail")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/test-unhandled-error")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "sensitive internal detail" not in response.text
    assert response.headers["x-request-id"]


def test_validation_errors_use_the_standard_error_envelope() -> None:
    application = create_app(
        Settings(
            app_env="test",
            log_level="INFO",
            cors_allowed_origins=("http://localhost:3000",),
        )
    )

    @application.get("/test-validation")
    async def validation_probe(quantity: int) -> dict[str, int]:
        return {"quantity": quantity}

    with TestClient(application) as client:
        response = client.get("/test-validation", params={"quantity": "not-an-int"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"][0]["location"] == ["query", "quantity"]
    assert "input" not in response.json()["error"]["details"][0]


def test_application_rejects_wildcard_cors_configuration(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValueError, match="Wildcard CORS"):
        Settings.from_environment()


def test_production_requires_explicit_cors_origins(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    with pytest.raises(ValueError, match="must be set in production"):
        Settings.from_environment()


def test_production_rejects_http_cors_origins(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings.from_environment()


def test_production_lifespan_uses_and_closes_injected_clock_monitor() -> None:
    class FakeClockMonitor:
        def __init__(self) -> None:
            self.started = False
            self.closed = False

        async def start(self) -> None:
            self.started = True

        async def close(self) -> None:
            self.closed = True

        def is_healthy(self) -> bool:
            return True

        @property
        def snapshot(self) -> ClockHealthSnapshot:
            return ClockHealthSnapshot(True, None, 0.0, 3, "healthy")

    monitor = FakeClockMonitor()
    settings = Settings(
        app_env="production",
        log_level="INFO",
        cors_allowed_origins=("https://baymax-nu.vercel.app",),
    )
    application = create_app(
        settings,
        clock_health_monitor_factory=lambda: cast(ClockHealthMonitor, monitor),
    )

    with TestClient(application):
        assert monitor.started is True
        assert application.state.clock_health_provider() is True

    assert monitor.closed is True


def test_production_swagger_and_openapi_are_public() -> None:
    settings = Settings(
        app_env="production",
        log_level="INFO",
        cors_allowed_origins=("https://baymax-nu.vercel.app",),
        session_secret="test-session-secret",
    )
    application = create_app(settings, clock_health_provider=lambda: False)

    with TestClient(application) as client:
        swagger = client.get("/docs")
        schema = client.get("/openapi.json")

    assert swagger.status_code == 200
    assert "swagger-ui" in swagger.text.lower()
    assert schema.status_code == 200
    assert "/api/v1/analysis/history" in schema.json()["paths"]


def test_production_gate_3_diagnostics_still_require_owner_session() -> None:
    settings = Settings(
        app_env="production",
        log_level="INFO",
        cors_allowed_origins=("https://baymax-nu.vercel.app",),
        session_secret="test-session-secret",
    )
    application = create_app(settings, clock_health_provider=lambda: False)

    with TestClient(application) as client:
        response = client.post("/api/v1/diagnostics/gate-3")

    assert response.status_code == 401


def test_durable_snapshot_verification_still_requires_owner_session() -> None:
    settings = Settings(
        app_env="production",
        log_level="INFO",
        cors_allowed_origins=("https://baymax-nu.vercel.app",),
        session_secret="test-session-secret",
    )
    application = create_app(settings, clock_health_provider=lambda: False)

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/diagnostics/gate-3/durable-snapshot",
            json={"confirm_durable_write": True},
        )

    assert response.status_code == 401



def test_websocket_rotation_diagnostic_still_requires_owner_session() -> None:
    settings = Settings(
        app_env="production",
        log_level="INFO",
        cors_allowed_origins=("https://baymax-nu.vercel.app",),
        session_secret="test-session-secret",
    )
    application = create_app(settings, clock_health_provider=lambda: False)

    with TestClient(application) as client:
        response = client.post("/api/v1/diagnostics/gate-3/websocket-rotation")

    assert response.status_code == 401
