import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.errors import AppError
from app.logging_config import configure_logging, request_logging_middleware
from app.routers import auth, budgets, categories, expenses, health, reports

logger = logging.getLogger("app")


def _error(status_code: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    """The single error envelope used for every non-2xx response."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=headers,
    )


def _field_name(loc: tuple) -> str:
    # ("body", "amount") -> "amount"; ("query", "limit") -> "limit"; ("body",) -> "body"
    parts = [str(part) for part in loc[1:]] if len(loc) > 1 else [str(part) for part in loc]
    return ".".join(parts)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return _error(exc.status_code, exc.code, exc.message, exc.details, headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # FastAPI's default 422 body echoes the submitted value ("input"), which
        # could be a password. Only the field and message are returned here.
        details = [
            {"field": _field_name(tuple(err["loc"])), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _error(422, "validation_error", "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "http_error", str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return _error(500, "internal_error", "Internal server error")


def create_app() -> FastAPI:
    settings = get_settings()  # fails fast on missing/invalid configuration (SEC-01)
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Expense Tracker API",
        version="1.0.0",
        description="Track expenses, set monthly budgets per category and view spending reports.",
    )
    app.middleware("http")(request_logging_middleware)
    register_exception_handlers(app)
    for module in (auth, categories, expenses, budgets, reports, health):
        app.include_router(module.router)
    return app


app = create_app()
