from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.models.artifact import Artifact
from app.models.run import Run
from app.ports import ArtifactRecord
from app.repositories.artifacts import list_artifacts
from app.schemas.artifacts import ArtifactList

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


def problem(code, key, message):
    return HTTPException(status_code=code, detail={"code": key, "message": message})


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactList)
def get_artifacts(run_id: UUID, session: Annotated[Session, Depends(get_session)]):
    if session.get(Run, run_id) is None:
        raise problem(404, "not_found", "Run not found")
    return {"items": list_artifacts(session, run_id)}


@router.get("/artifacts/{artifact_id}/content")
def get_content(
    artifact_id: UUID, request: Request, session: Annotated[Session, Depends(get_session)]
):
    item = session.get(Artifact, artifact_id)
    if item is None:
        raise problem(404, "not_found", "Artifact not found")
    if item.size_bytes > 1024 * 1024:
        raise problem(413, "too_big", "Text preview limit is 1 MiB")
    record = ArtifactRecord(
        f"{item.run_id}/{item.path}", item.mime_type, item.size_bytes, item.sha256
    )
    try:
        path = request.app.state.storage.verified_path(record)
        data = path.read_bytes()
    except (AppError, FileNotFoundError):
        raise problem(409, "artifact_invalid", "Artifact path or hash is invalid") from None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise problem(400, "invalid_input", "Only UTF-8 text can be previewed") from None
    media = "application/json" if item.mime_type == "application/json" else "text/plain"
    return Response(
        data,
        media_type=media,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
