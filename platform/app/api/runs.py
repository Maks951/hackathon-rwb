from typing import Annotated
from uuid import UUID
from app.repositories.runs import get_run as get_run_by_id
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from fastapi import Query
from app.schemas.run_events import EventList
from app.repositories.run_events import list_events
from app.schemas.run_events import EventList

from app.db import get_session
from app.repositories.runs import (
    ProjectNotFound,
    RunConflict,
    create_run_with_snapshot,
)
from app.schemas.runs import RunRead

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunRead,
    status_code=202,
)
def create_run(
    project_id: UUID,
    idempotency_key: Annotated[
        UUID, Header(alias="Idempotency-Key")
    ],
    session: Session = Depends(get_session),
):
    try:
        return create_run_with_snapshot(
            session,
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
    except ProjectNotFound:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Проект не найден",
            },
        )
    except RunConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "conflict",
                "message": str(exc),
            },
        )
@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(
    run_id: UUID,
    session: Session = Depends(get_session),
):
    run = get_run_by_id(session, run_id)

    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Запуск не найден",
            },
        )

    return run
@router.get(
    "/runs/{run_id}/events",
    response_model=EventList,
)
def get_run_events(
    run_id: UUID,
    after_sequence: int = Query(
        default=0,
        alias="afterSequence",
        ge=0,
    ),
    session: Session = Depends(get_session),
):
    if get_run_by_id(session, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Запуск не найден",
            },
        )

    events = list_events(
        session,
        run_id=run_id,
        after_sequence=after_sequence,
    )

    return {
        "items": events,
        "next_sequence": (
            events[-1].sequence if events else after_sequence
        ),
    }