from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

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
        "/api/v1/auth/login",
        "/api/v1/auth/session",
        "/api/v1/auth/logout",
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
