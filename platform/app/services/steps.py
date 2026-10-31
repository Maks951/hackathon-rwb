import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.config import Settings
from app.errors import AppError, ProviderError, safe_error
from app.ports import (
    ArtifactRecord,
    GenerationAdapter,
    GenerationRequest,
    GenerationStage,
    RunRepository,
)
from app.schemas.runs import ErrorDto
from app.services.storage import StageFiles, Storage


@dataclass(frozen=True)
class StepResult:
    output: dict[str, Any]
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: ErrorDto | None = None


class StepExecutor:
    def __init__(
        self,
        repository: RunRepository,
        generation: GenerationAdapter,
        storage: Storage,
        settings: Settings,
    ):
        self.repository = repository
        self.generation = generation
        self.storage = storage
        self.settings = settings

    async def execute(
        self,
        run_id: UUID,
        key: str,
        attempt: int,
        inputs: dict[str, Any],
        operation: Callable[[], Awaitable[StepResult]],
    ) -> str:
        prefix = f"{run_id}/steps/{key}/{attempt:03d}"
        saved_input = self.storage.write_json(f"{prefix}/input.json", inputs)
        step = await self.repository.start_step(
            run_id, key, attempt, saved_input.path, datetime.now(UTC)
        )
        try:
            result = await operation()
            saved_output = self.storage.write_json(f"{prefix}/output.json", result.output)
            await self.repository.complete_step(
                step.id,
                saved_output.path,
                {
                    **result.metadata,
                    "inputSha256": saved_input.sha256,
                    "outputSha256": saved_output.sha256,
                },
                [saved_input, saved_output, *result.artifacts],
                datetime.now(UTC),
                error=result.error,
            )
            return saved_output.path
        except asyncio.CancelledError:
            await self.repository.fail_step(
                step.id,
                AppError("step_interrupted", "Выполнение этапа прервано.").error,
                datetime.now(UTC),
            )
            raise
        except Exception as exc:
            await self.repository.fail_step(step.id, safe_error(exc), datetime.now(UTC))
            raise

    async def generate(
        self,
        run_id: UUID,
        stage: GenerationStage,
        attempt: int,
        inputs: dict[str, Any],
    ) -> str:
        async def operation() -> StepResult:
            # The model receives the exact persisted input, not mutable live project state.
            input_path = f"{run_id}/steps/{stage}/{attempt:03d}/input.json"
            request = GenerationRequest(stage, self.storage.read_json(input_path))
            artifacts: list[ArtifactRecord] = []
            calls: list[dict[str, Any]] = []
            transient_retries = 0
            json_retries = 0
            call = 0
            while True:
                call += 1
                started_at = time.perf_counter()
                try:
                    async with asyncio.timeout(self.settings.llm_timeout_seconds):
                        response = await self.generation.generate(request)
                except (ProviderError, TimeoutError) as exc:
                    transient = isinstance(exc, TimeoutError) or exc.transient
                    # At most two retries for the whole step, including a JSON correction call.
                    if not transient or transient_retries >= 2:
                        raise ProviderError() from None
                    transient_retries += 1
                    await self.repository.add_event(
                        run_id, "provider_retry", "Повтор запроса генерации."
                    )
                    await asyncio.sleep(2 ** (transient_retries - 1))
                    continue
                if len(response.content.encode()) > self.settings.max_response_bytes:
                    raise AppError("output_too_large", "Ответ модели превышает лимит.", 413)
                if not response.model_id or not response.prompt_version:
                    raise AppError("invalid_metadata", "Адаптер не указал модель и версию промпта.")
                call_path = f"{run_id}/steps/{stage}/{attempt:03d}/call-{call:02d}.json"
                artifacts.append(self.storage.write_json(call_path, asdict(response)))
                calls.append(
                    {
                        "modelId": response.model_id,
                        "promptVersion": response.prompt_version,
                        "inputTokens": response.input_tokens,
                        "outputTokens": response.output_tokens,
                        "sha256": artifacts[-1].sha256,
                        "elapsedMs": round((time.perf_counter() - started_at) * 1000),
                    }
                )
                await self.repository.record_call(run_id, stage, attempt, calls[-1], artifacts[-1])
                if response.finish_reason != "stop":
                    raise AppError(
                        "truncated_response", "Генерация не завершена: ответ модели обрезан."
                    )
                try:
                    output = self.generation.output_schema(stage).model_validate_json(
                        response.content
                    )
                    payload = output.model_dump(mode="json", by_alias=True)
                except ValidationError as exc:
                    # Report schema locations/codes, never rejected input values or context.
                    errors = tuple(
                        f"{'.'.join(map(str, e['loc']))}: {e['type']}"
                        for e in exc.errors(include_input=False, include_context=False)[:20]
                    )
                    if json_retries >= 1:
                        raise AppError(
                            "invalid_model_output",
                            "Ответ модели не соответствует схеме: " + "; ".join(errors),
                        ) from None
                    json_retries += 1
                    request = GenerationRequest(stage, request.inputs, errors, response.content)
                    await self.repository.add_event(
                        run_id, "json_retry", "Исправление структуры JSON."
                    )
                    continue
                if stage not in ("analyze", "design"):
                    try:
                        files = StageFiles.model_validate(payload)
                    except ValidationError:
                        raise AppError(
                            "invalid_model_output", "Ожидается результат StageFiles."
                        ) from None
                    self.storage.validate_files(stage, files)
                return StepResult(
                    payload,
                    artifacts,
                    {
                        "calls": calls,
                        "transientRetries": transient_retries,
                        "jsonRetries": json_retries,
                    },
                )

        return await self.execute(run_id, stage, attempt, inputs, operation)
