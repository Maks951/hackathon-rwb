from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import FileResponse

from app.errors import AppError, IntegrationUnavailable
from app.ports import RunRecord, RunRepository
from app.schemas.runs import (
    CreateRunDto,
    EventsDto,
    RunDetailsDto,
    RunDto,
    StepDto,
)

router = APIRouter(prefix="/api/v1", tags=["runs"])


def repository(request: Request) -> RunRepository:
    repo = request.app.state.runtime.repository
    if repo is None:
        raise IntegrationUnavailable("repository")
    return repo


Repository = Annotated[RunRepository, Depends(repository)]


def run_dto(run: RunRecord) -> RunDto:
    # Snapshot requirements and internal metadata must not accidentally enter the DTO.
    return RunDto(**{name: getattr(run, name) for name in RunDto.model_fields})


async def require_run(repo: RunRepository, run_id: UUID) -> RunRecord:
    run = await repo.get_run(run_id)
    if run is None:
        raise AppError("not_found", "Запуск не найден.", 404)
    return run


@router.post("/projects/{project_id}/runs", status_code=202, response_model=RunDto)
async def create_run(
    project_id: UUID,
    body: CreateRunDto,
    response: Response,
    repo: Repository,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> RunDto:
    run = await repo.create_run(project_id, idempotency_key)
    response.headers["Location"] = f"/api/v1/runs/{run.id}"
    return run_dto(run)


@router.get("/runs/{run_id}", response_model=RunDetailsDto)
async def get_run(run_id: UUID, repo: Repository) -> RunDetailsDto:
    run = await require_run(repo, run_id)
    steps = [StepDto.model_validate(step) for step in await repo.list_steps(run_id)]
    return RunDetailsDto(
        **run_dto(run).model_dump(by_alias=False),
        steps=steps,
        validation_status=run.validation_status,
        deployment_status=run.deployment_status,
    )


@router.get("/runs/{run_id}/events", response_model=EventsDto)
async def get_events(
    run_id: UUID,
    request: Request,
    repo: Repository,
    after_sequence: Annotated[int, Query(alias="afterSequence", ge=0)] = 0,
) -> EventsDto:
    await require_run(repo, run_id)
    items = await repo.list_events(run_id, after_sequence, request.app.state.settings.max_events)
    return EventsDto(items=items, next_sequence=items[-1].sequence if items else after_sequence)


@router.get("/runs/{run_id}/download", response_class=FileResponse)
async def download_run(run_id: UUID, request: Request, repo: Repository) -> FileResponse:
    await require_run(repo, run_id)
    artifact = await repo.get_package(run_id)
    if artifact is None:
        raise AppError("package_not_ready", "Архив запуска ещё не готов.", 409)
    path = request.app.state.storage.verified_path(artifact)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{run_id}.zip",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
