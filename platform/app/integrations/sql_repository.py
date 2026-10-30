"""SQLAlchemy adapter for Yaroslav's async RunRepository port.

Sessions live only inside a to_thread call; no DB transaction spans a model call.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.errors import AppError, IntegrationUnavailable
from app.models.artifact import Artifact
from app.models.project import Project
from app.models.run import Run
from app.models.run_event import RunEvent
from app.models.step import Step
from app.ports import ArtifactRecord, RunRecord
from app.repositories.runs import ProjectNotFound, RunConflict, create_run_with_snapshot
from app.schemas.runs import (
    DeploymentStatus,
    ErrorDto,
    EventDto,
    RunStatus,
    StepDto,
    ValidationStatus,
)
from app.services.storage import Storage


def utc(value):
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def decode_error(value: str | None) -> ErrorDto | None:
    if value is None:
        return None
    try:
        return ErrorDto.model_validate_json(value)
    except ValueError:
        return ErrorDto(code="internal_error", message="Ошибка выполнения этапа.")


def encode_error(value: ErrorDto | None) -> str | None:
    return value.model_dump_json() if value is not None else None


def run_record(run: Run) -> RunRecord:
    return RunRecord(
        id=run.id,
        project_id=run.project_id,
        requirements_snapshot=run.requirements_snapshot,
        status=RunStatus(run.status),
        created_at=utc(run.created_at),
        current_step=run.current_step,
        error=decode_error(run.error),
        repository_url=run.repository_url,
        preview_url=run.preview_url,
        finished_at=utc(run.finished_at),
        validation_status=ValidationStatus(run.validation_status),
        deployment_status=DeploymentStatus(run.deployment_status),
    )


def step_dto(step: Step) -> StepDto:
    return StepDto(
        id=step.id,
        key=step.key,
        attempt=step.attempt,
        status=step.status,
        error=decode_error(step.error),
    )


class SqlRunRepository:
    def __init__(self, settings: Settings, *, factory=None):
        self.storage = Storage(settings)
        if factory is None:
            if not settings.database_url:
                raise IntegrationUnavailable("DATABASE_URL")
            options = {}
            if settings.database_url.startswith("postgresql"):
                options["connect_args"] = {
                    "connect_timeout": settings.database_connect_timeout_seconds
                }
            self.engine = create_engine(settings.database_url, pool_pre_ping=True, **options)
            self.factory = sessionmaker(self.engine, expire_on_commit=False)
        else:
            self.engine = None
            self.factory = factory

    def close(self):
        if self.engine is not None:
            self.engine.dispose()

    async def _call(self, name, *args):
        try:
            return await asyncio.to_thread(self._transaction, name, args)
        except ProjectNotFound:
            raise AppError("not_found", "Проект не найден.", 404) from None
        except RunConflict:
            raise AppError("conflict", "Ключ или активный запуск конфликтует.", 409) from None
        except IntegrityError:
            raise AppError(
                "conflict", "Изменение конфликтует с сохранёнными данными.", 409
            ) from None
        except SQLAlchemyError:
            raise AppError(
                "database_unavailable", "База данных временно недоступна.", 503
            ) from None

    def _transaction(self, name, args):
        with self.factory() as session:
            if name == "create_run":
                # Existing repository owns commit and race handling.
                run = create_run_with_snapshot(session, project_id=args[0], idempotency_key=args[1])
                return run_record(run)
            with session.begin():
                return getattr(self, "_" + name)(session, *args)

    @staticmethod
    def _run(session, run_id, *, running=False):
        run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if run is None:
            raise AppError("not_found", "Запуск не найден.", 404)
        if running and run.status != "running":
            raise AppError("worker_interrupted", "Запуск больше не выполняется.", 409)
        return run

    @staticmethod
    def _event(session, run_id, event_type, message):
        # Caller owns the Run lock; sequence allocation is serialized per run.
        sequence = session.scalar(
            select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
        )
        session.add(
            RunEvent(run_id=run_id, sequence=(sequence or 0) + 1, type=event_type, message=message)
        )

    def _artifact(self, session, run_id, item, step_id=None):
        prefix = f"{run_id}/"
        if not item.path.startswith(prefix):
            raise AppError("unsafe_path", "Артефакт не принадлежит запуску.", 400)
        self.storage.verified_path(item)
        relative = item.path[len(prefix) :]
        existing = session.scalar(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.path == relative)
        )
        if existing is not None:
            if existing.sha256 != item.sha256 or existing.size_bytes != item.size_bytes:
                raise AppError("artifact_corrupt", "Неизменяемый артефакт был заменён.", 409)
            # Validation/package may reference the same immutable workspace file.
            # Keep its original owning step instead of reassigning it.
            if step_id is not None and existing.step_id is None:
                existing.step_id = step_id
            return existing
        existing = Artifact(
            run_id=run_id,
            step_id=step_id,
            path=relative,
            mime_type=item.mime_type,
            size_bytes=item.size_bytes,
            sha256=item.sha256,
        )
        session.add(existing)
        return existing

    def _step(self, session, step_id):
        step = session.get(Step, step_id)
        if step is None:
            raise AppError("not_found", "Этап не найден.", 404)
        self._run(session, step.run_id, running=True)
        # All mutations take the parent lock first.
        session.refresh(step)
        if step.status != "running":
            raise AppError("conflict", "Этап уже завершён.", 409)
        return step

    def _ping(self, session):
        for model in (Project, Run, Step, RunEvent, Artifact):
            session.execute(select(model).limit(1))
        return True

    def _get_run(self, session, run_id):
        run = session.get(Run, run_id)
        return run_record(run) if run else None

    def _list_steps(self, session, run_id):
        return [
            step_dto(s)
            for s in session.scalars(
                select(Step).where(Step.run_id == run_id).order_by(Step.key, Step.attempt)
            )
        ]

    def _list_events(self, session, run_id, after, limit):
        if after < 0 or not 1 <= limit <= 1000:
            raise AppError("invalid_input", "Некорректный курсор событий.", 400)
        return [
            EventDto(
                id=e.id,
                sequence=e.sequence,
                type=e.type,
                message=e.message,
                created_at=utc(e.created_at),
            )
            for e in session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.sequence > after)
                .order_by(RunEvent.sequence)
                .limit(limit)
            )
        ]

    def _get_package(self, session, run_id):
        run = session.get(Run, run_id)
        if run is None:
            return None
        if run.validation_status != "passed" or not run.package_path:
            return None
        path = run.package_path
        item = session.scalar(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.path == path)
        )
        if item is None:
            return None
        return ArtifactRecord(f"{run_id}/{item.path}", item.mime_type, item.size_bytes, item.sha256)

    def _claim_next(self, session):
        run = session.scalar(
            select(Run)
            .where(Run.status == "queued")
            .order_by(Run.created_at, Run.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if run is None:
            return None
        run.status = "running"
        run.heartbeat_at = datetime.now(UTC)
        self._event(session, run.id, "run_started", "Запуск получен worker.")
        session.flush()
        return run_record(run)

    def _heartbeat(self, session, run_id, now):
        run = self._run(session, run_id)
        if run.status != "running":
            return False
        run.heartbeat_at = now
        return True

    def _fail_stale(self, session, before, now):
        runs = list(
            session.scalars(
                select(Run)
                .where(
                    Run.status == "running",
                    func.coalesce(Run.heartbeat_at, Run.created_at) < before,
                )
                .with_for_update(skip_locked=True)
            )
        )
        error = ErrorDto(code="worker_interrupted", message="Worker перестал отправлять heartbeat.")
        for run in runs:
            self._finish(session, run, RunStatus.FAILED, error, now)
        return len(runs)

    def _start_step(self, session, run_id, key, attempt, input_path, now):
        run = self._run(session, run_id, running=True)
        if not key or len(key) > 80 or attempt < 1:
            raise AppError("invalid_input", "Некорректный этап.", 400)
        self.storage.path(input_path)  # Also rejects invalid paths and symlinks.
        if not input_path.startswith(f"{run_id}/"):
            raise AppError("unsafe_path", "Вход этапа не принадлежит запуску.", 400)
        existing = session.scalar(
            select(Step).where(Step.run_id == run_id, Step.key == key, Step.attempt == attempt)
        )
        if existing is not None:
            raise AppError("conflict", "Эта попытка этапа уже существует.", 409)
        step = Step(
            run_id=run_id,
            key=key,
            attempt=attempt,
            status="running",
            input_path=input_path,
            started_at=now,
            metadata_json={},
        )
        session.add(step)
        run.current_step = key
        self._event(session, run_id, "step_started", f"Этап {key}, попытка {attempt}.")
        session.flush()
        return step_dto(step)

    def _complete_step(self, session, step_id, output_path, metadata, artifacts, now, error):
        step = self._step(session, step_id)
        if not any(a.path == output_path for a in artifacts):
            raise AppError("artifact_missing", "В manifest нет результата этапа.", 409)
        for artifact in artifacts:
            self._artifact(session, step.run_id, artifact, step.id)
        step.output_path = output_path
        step.metadata_json = {**(step.metadata_json or {}), **metadata}
        step.status = "failed" if error else "succeeded"
        step.error = encode_error(error)
        step.finished_at = now
        self._event(session, step.run_id, "step_finished", f"Этап {step.key}: {step.status}.")

    def _record_call(self, session, run_id, key, attempt, metadata, artifact):
        self._run(session, run_id, running=True)
        step = session.scalar(
            select(Step).where(Step.run_id == run_id, Step.key == key, Step.attempt == attempt)
        )
        if step is None or step.status != "running":
            raise AppError("conflict", "Нет работающей попытки этапа.", 409)
        self._artifact(session, run_id, artifact, step.id)
        data = dict(step.metadata_json or {})
        data["calls"] = [*data.get("calls", []), metadata]
        step.metadata_json = data

    def _fail_step(self, session, step_id, error, now):
        step = session.get(Step, step_id)
        if step is None:
            raise AppError("not_found", "Этап не найден.", 404)
        run = self._run(session, step.run_id)
        session.refresh(step)
        if step.status != "running" or run.status != "running":
            return  # Do not overwrite terminal steps after stale recovery.
        step.status = "failed"
        step.error = encode_error(error)
        step.finished_at = now
        self._event(session, run.id, "step_failed", f"Этап {step.key} завершился ошибкой.")

    def _add_event(self, session, run_id, event_type, message):
        self._run(session, run_id, running=True)
        self._event(session, run_id, event_type, message)

    def _set_validation(self, session, run_id, status):
        self._run(session, run_id, running=True).validation_status = ValidationStatus(status).value

    def _set_deployment(self, session, run_id, status, preview_url):
        run = self._run(session, run_id, running=True)
        run.deployment_status = DeploymentStatus(status).value
        run.preview_url = preview_url

    def _set_repository_url(self, session, run_id, url):
        self._run(session, run_id, running=True).repository_url = url

    def _save_package(self, session, run_id, artifact):
        run = self._run(session, run_id, running=True)
        if run.validation_status != "passed":
            raise AppError(
                "validation_required", "Нельзя сохранить пакет до успешных проверок.", 409
            )
        if (
            artifact.path != f"{run_id}/package/product.zip"
            or artifact.mime_type != "application/zip"
        ):
            raise AppError("invalid_package", "Некорректный пакет.", 409)
        self._artifact(session, run_id, artifact)
        run.package_path = "package/product.zip"

    def _finish(self, session, run, status, error, now):
        if status not in (RunStatus.SUCCEEDED, RunStatus.FAILED):
            raise AppError("invalid_input", "Ожидается конечный статус.", 400)
        if status == RunStatus.SUCCEEDED and (
            run.validation_status != "passed" or not run.package_path or error
        ):
            raise AppError(
                "validation_required", "Нужны успешные проверки и зарегистрированный ZIP.", 409
            )
        active = list(
            session.scalars(select(Step).where(Step.run_id == run.id, Step.status == "running"))
        )
        if status == RunStatus.SUCCEEDED and active:
            raise AppError("conflict", "Есть незавершённые этапы.", 409)
        for step in active:
            step.status = "failed"
            step.error = encode_error(error)
            step.finished_at = now
        run.status = status.value
        run.current_step = None
        run.error = encode_error(error)
        run.finished_at = now
        self._event(session, run.id, "run_finished", f"Запуск: {status.value}.")

    def _finish_run(self, session, run_id, status, error, now):
        run = self._run(session, run_id)
        if run.status != "running":
            return
        self._finish(session, run, RunStatus(status), error, now)

    async def ping(self):
        return await self._call("ping")

    async def create_run(self, project_id, idempotency_key):
        return await self._call("create_run", project_id, idempotency_key)

    async def get_run(self, run_id):
        return await self._call("get_run", run_id)

    async def list_steps(self, run_id):
        return await self._call("list_steps", run_id)

    async def list_events(self, run_id, after, limit):
        return await self._call("list_events", run_id, after, limit)

    async def get_package(self, run_id):
        return await self._call("get_package", run_id)

    async def claim_next(self):
        return await self._call("claim_next")

    async def heartbeat(self, run_id, now):
        return await self._call("heartbeat", run_id, now)

    async def fail_stale(self, before, now):
        return await self._call("fail_stale", before, now)

    async def start_step(self, run_id, key, attempt, input_path, now):
        return await self._call("start_step", run_id, key, attempt, input_path, now)

    async def complete_step(self, step_id, output_path, metadata, artifacts, now, error=None):
        return await self._call(
            "complete_step", step_id, output_path, metadata, artifacts, now, error
        )

    async def record_call(self, run_id, key, attempt, metadata, artifact):
        return await self._call("record_call", run_id, key, attempt, metadata, artifact)

    async def fail_step(self, step_id, error, now):
        return await self._call("fail_step", step_id, error, now)

    async def add_event(self, run_id, type, message):
        return await self._call("add_event", run_id, type, message)

    async def set_validation(self, run_id, status):
        return await self._call("set_validation", run_id, status)

    async def set_deployment(self, run_id, status, preview_url):
        return await self._call("set_deployment", run_id, status, preview_url)

    async def set_repository_url(self, run_id, url):
        return await self._call("set_repository_url", run_id, url)

    async def save_package(self, run_id, artifact):
        return await self._call("save_package", run_id, artifact)

    async def finish_run(self, run_id, status, error, now):
        return await self._call("finish_run", run_id, status, error, now)
