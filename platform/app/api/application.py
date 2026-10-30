import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.projects import router as projects_router
from app.api.runs import router
from app.composition import load_runtime
from app.config import Settings
from app.errors import AppError, safe_error
from app.integrations.projects import install_projects
from app.ports import Runtime
from app.schemas.runs import ErrorDto, HealthDto
from app.services.storage import Storage

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or Settings()
    runtime = runtime if runtime is not None else load_runtime(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Queue work runs in `python -m app.worker`, never an API background task.
        try:
            yield
        finally:
            close_database()

    errors = {code: {"model": ErrorDto} for code in (400, 404, 409, 413, 500, 502, 503)}
    app = FastAPI(
        title="RWB Platform Runs API", version="1.0.0", lifespan=lifespan, responses=errors
    )
    app.state.settings = settings
    app.state.runtime = runtime
    app.state.storage = Storage(settings)
    project_readiness, close_database = install_projects(app, settings)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Idempotency-Key"],
            expose_headers=["Location"],
        )

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(exc.error.model_dump(mode="json"), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic errors contain input values: don't reflect bodies/tokens in API errors.
        return JSONResponse(
            ErrorDto(code="invalid_input", message="Некорректные параметры запроса.").model_dump(
                mode="json"
            ),
            status_code=400,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and set(exc.detail) <= {"code", "message", "details"}:
            try:
                error = ErrorDto.model_validate(exc.detail)
            except ValueError:
                error = ErrorDto(code="http_error", message="Запрос не может быть выполнен.")
        else:
            error = ErrorDto(code="http_error", message="Запрос не может быть выполнен.")
        return JSONResponse(
            error.model_dump(mode="json"),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled API exception (%s)", type(exc).__name__)
        return JSONResponse(safe_error(exc).model_dump(mode="json"), status_code=500)

    @app.get("/health", response_model=HealthDto, responses={503: {"model": HealthDto}})
    async def health() -> JSONResponse:
        try:
            ready = (
                await runtime.repository.ping()
                if runtime.repository is not None
                else await project_readiness()
            )
        except Exception:
            ready = False
        return JSONResponse(
            {"status": "ok" if ready else "not_ready"}, status_code=200 if ready else 503
        )

    app.include_router(router)
    for extra_router in runtime.routers:
        if extra_router is not projects_router:
            app.include_router(extra_router)  # Additional artifact/auth APIs.

    original_openapi = app.openapi

    def openapi() -> dict:
        schema = original_openapi()
        # FastAPI's automatic 422 is replaced by our safe 400 handler.
        for path in schema.get("paths", {}).values():
            for operation in path.values():
                if isinstance(operation, dict):
                    operation.get("responses", {}).pop("422", None)
        return schema

    app.openapi = openapi
    return app
