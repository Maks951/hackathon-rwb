from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_session
from app.models.artifact import Artifact
from app.models.run import Run
from app.repositories.artifacts import PACKAGE_PATH, artifact_path, checked_bytes, list_artifacts
from app.schemas.artifacts import ArtifactList

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


def problem(code: int, key: str, message: str):
    return HTTPException(status_code=code, detail={"code": key, "message": message})


def read_checked(item: Artifact) -> bytes:
    try:
        return checked_bytes(item)
    except FileNotFoundError:
        raise problem(404, "not_found", "Artifact file missing")
    except ValueError:
        raise problem(409, "artifact_invalid", "Artifact path or hash is invalid")


@router.get("/runs/{run_id}/artifacts", response_model=ArtifactList)
def get_artifacts(run_id: UUID, session: Session = Depends(get_session)):
    if session.get(Run, run_id) is None:
        raise problem(404, "not_found", "Run not found")
    return {"items": list_artifacts(session, run_id)}


@router.get("/artifacts/{artifact_id}/content")
def get_content(artifact_id: UUID, session: Session = Depends(get_session)):
    item = session.get(Artifact, artifact_id)
    if item is None:
        raise problem(404, "not_found", "Artifact not found")
    if item.size_bytes > 1024 * 1024:
        raise problem(413, "too_big", "Text preview limit is 1 MiB")
    try:
        target = artifact_path(item.run_id, item.path)
        if target.stat().st_size > 1024 * 1024:
            raise problem(413, "too_big", "Text preview limit is 1 MiB")
    except FileNotFoundError:
        raise problem(404, "not_found", "Artifact file missing")
    except ValueError:
        raise problem(409, "artifact_invalid", "Unsafe artifact path")
    data = read_checked(item)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise problem(400, "invalid_input", "Only UTF-8 text can be previewed")
    media = "application/json" if item.mime_type == "application/json" else "text/plain"
    return Response(data, media_type=media, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/runs/{run_id}/download")
def download(run_id: UUID, session: Session = Depends(get_session)):
    if session.get(Run, run_id) is None:
        raise problem(404, "not_found", "Run not found")
    item = session.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.path == PACKAGE_PATH))
    if item is None:
        raise problem(409, "not_ready", "Package is not ready")
    return Response(read_checked(item), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{run_id}.zip"',
        "X-Content-Type-Options": "nosniff",
    })
