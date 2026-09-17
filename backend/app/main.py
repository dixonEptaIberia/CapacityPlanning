"""FastAPI application entry point.

Assembles middleware, structured error handling (R5.2), CORS (R5.5), the health
check (R5.3), and the API routers. Auto-generated OpenAPI is served at
``/openapi.json`` and docs at ``/docs`` (R5.4).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_correlation_id, new_correlation_id
from app.db.base import init_db
from app.domain.rules import RuleError
from app.routers import config as config_router
from app.routers import (
    exports,
    grid,
    imports,
    notes,
    plants,
    regional,
    scenarios,
    transfers,
    versions,
)

configure_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # For dev/demo. Production uses Alembic migrations.
    init_db()
    from app.seed import seed_if_empty

    seed_if_empty()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = new_correlation_id()
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = cid
    return response


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": get_correlation_id(),
            }
        },
    )


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(RuleError)
async def handle_rule_error(_: Request, exc: RuleError) -> JSONResponse:
    # Business-rule violations are client errors (invalid input).
    return _error_response(400, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(400, "validation_error", str(exc.errors()))


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return _error_response(500, "internal_error", "An unexpected error occurred.")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Service health check (R5.3)."""
    return {"status": "ok"}


# Routers
app.include_router(plants.router)
app.include_router(grid.router)
app.include_router(regional.router)
app.include_router(transfers.router)
app.include_router(notes.router)
app.include_router(scenarios.router)
app.include_router(versions.router)
app.include_router(imports.router)
app.include_router(exports.router)
app.include_router(config_router.router)
