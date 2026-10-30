"""Composition of Roman's unchanged router/repository into the production app."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import contextmanager

from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.api.projects import router
from app.config import Settings
from app.db import get_session
from app.errors import AppError, IntegrationUnavailable
from app.models.project import Project


def install_projects(
    app: FastAPI, settings: Settings
) -> tuple[Callable[[], Awaitable[bool]], Callable]:
    options = {}
    if settings.database_url and settings.database_url.startswith("postgresql"):
        options["connect_args"] = {"connect_timeout": settings.database_connect_timeout_seconds}
    engine = (
        create_engine(settings.database_url, pool_pre_ping=True, **options)
        if settings.database_url
        else None
    )
    factory = sessionmaker(engine, expire_on_commit=False) if engine is not None else None

    @contextmanager
    def session():
        if factory is None:
            raise IntegrationUnavailable("DATABASE_URL")
        try:
            with factory() as value:
                yield value
        except SQLAlchemyError:
            raise AppError(
                "database_unavailable", "База данных временно недоступна.", 503
            ) from None

    def dependency():
        with session() as value:
            yield value

    def check() -> bool:
        with session() as value:
            # SELECT 1 alone doesn't prove the migrations have been applied.
            value.execute(select(Project.id).limit(1))
        return True

    async def ready() -> bool:
        return await asyncio.to_thread(check)

    def close() -> None:
        if engine is not None:
            engine.dispose()

    app.dependency_overrides[get_session] = dependency
    app.include_router(router)
    return ready, close
