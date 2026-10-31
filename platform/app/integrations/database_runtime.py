"""Explicit production runtime factory: SQL storage + existing Qwen adapter."""

from app.api.artifacts import router
from app.integrations.sql_repository import SqlRunRepository
from app.ports import Runtime


def create_runtime(settings):
    generation = None
    if settings.qwen_base_url and settings.qwen_model and settings.qwen_api_key:
        from app.llm.factory import create_qwen_adapter

        generation = create_qwen_adapter(settings)
    validator = None
    if settings.runner_url:
        from app.integrations.validation_runner import HttpValidationRunner

        validator = HttpValidationRunner(settings)
    return Runtime(
        validator=validator,
        repository=SqlRunRepository(settings),
        generation=generation,
        routers=(router,),
    )
