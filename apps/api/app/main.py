"""FastAPI application factory and HTTP infrastructure."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.auth.security import LoginRateLimiter
from app.core.config import Settings
from app.core.logging import configure_logging, request_id_context
from app.schemas.errors import ErrorDetail, ErrorResponse, ValidationIssue


def _request_id(request: Request) -> str:
    """Return the request ID assigned by the middleware."""
    return str(getattr(request.state, "request_id", "unknown"))


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable Baymax API application."""
    active_settings = settings or Settings.from_environment()
    app_logger = configure_logging(active_settings.log_level)

    application = FastAPI(
        title="Baymax API",
        summary="Versioned API for the Baymax trading intelligence workspace.",
        description=(
            "Phase 1 foundation. Public liveness and single-owner authentication "
            "endpoints are implemented. Private application operations remain "
            "unavailable until their approved implementation gates."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    application.state.settings = active_settings
    application.state.login_limiter = LoginRateLimiter()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(api_router)

    @application.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started_at = perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            app_logger.info(
                "request.completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                    "request_id": request_id,
                },
            )
            return response
        finally:
            request_id_context.reset(token)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        status_code = exc.status_code
        code_by_status = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            422: "validation_error",
            429: "too_many_requests",
            503: "service_unavailable",
        }
        safe_messages = {
            400: "The request could not be completed.",
            401: "Authentication is required.",
            403: "You are not permitted to perform this action.",
            404: "The requested resource was not found.",
            405: "The requested method is not allowed.",
            422: "Request validation failed.",
            429: "Too many requests. Try again later.",
            503: "The requested service is not configured or temporarily unavailable.",
        }
        message = safe_messages.get(status_code, "The request could not be completed.")
        payload = ErrorResponse(
            error=ErrorDetail(
                code=code_by_status.get(status_code, "http_error"),
                message=message,
                request_id=_request_id(request),
            )
        )
        return JSONResponse(
            status_code=status_code,
            content=payload.model_dump(mode="json", exclude_none=True),
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        issues = [
            ValidationIssue(
                location=[part if isinstance(part, int) else str(part) for part in item["loc"]],
                message=item["msg"],
                code=item["type"],
            )
            for item in exc.errors()
        ]
        payload = ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="Request validation failed.",
                request_id=_request_id(request),
                details=issues,
            )
        )
        return JSONResponse(
            status_code=422,
            content=payload.model_dump(mode="json", exclude_none=True),
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        app_logger.error(
            "request.unhandled_exception",
            extra={"request_id": _request_id(request), "exception_type": type(exc).__name__},
        )
        payload = ErrorResponse(
            error=ErrorDetail(
                code="internal_error",
                message="An unexpected server error occurred.",
                request_id=_request_id(request),
            )
        )
        return JSONResponse(
            status_code=500,
            content=payload.model_dump(mode="json", exclude_none=True),
            headers={"X-Request-ID": _request_id(request)},
        )

    return application


app = create_app()
