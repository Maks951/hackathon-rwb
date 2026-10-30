import hashlib
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.run import Run
from app.models.step import Step

PACKAGE_PATH = "_package/result.zip"


class UnsafeArtifactPath(ValueError):
    pass


def artifact_path(run_id: UUID, relative: str) -> Path:
    root = Path(
        os.environ.get("RWB_GENERATED_ROOT", os.environ.get("GENERATED_ROOT", "generated"))
    ).absolute()
    parts = PurePosixPath(relative).parts
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or relative.startswith("/")
        or ".." in parts
        or not parts
        or PurePosixPath(relative).as_posix() != relative
    ):
        raise UnsafeArtifactPath("Expected a normalized relative artifact path")
    base = root / str(run_id)
    target = base.joinpath(*parts)
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise UnsafeArtifactPath("Symlink paths are forbidden")
    if not target.resolve().is_relative_to(base.resolve()):
        raise UnsafeArtifactPath("Artifact escapes run directory")
    return target


def checked_bytes(artifact: Artifact) -> bytes:
    data = artifact_path(artifact.run_id, artifact.path).read_bytes()
    if len(data) != artifact.size_bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise ValueError("Artifact differs from registered metadata")
    return data


def register_artifact(
    session: Session,
    *,
    run_id: UUID,
    path: str,
    mime_type: str = "text/plain",
    step_id: UUID | None = None,
) -> Artifact:
    # The producer must finish temp -> rename before registering metadata.
    target = artifact_path(run_id, path)
    if target.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Artifact limit is 50 MiB")
    data = target.read_bytes()
    if not mime_type or len(mime_type) > 120:
        raise ValueError("Invalid MIME type")
    with session.begin():
        if session.scalar(select(Run.id).where(Run.id == run_id).with_for_update()) is None:
            raise LookupError("Run not found")
        if step_id is not None:
            step = session.get(Step, step_id)
            if step is None or step.run_id != run_id:
                raise ValueError("Step does not belong to run")
        item = session.scalar(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.path == path)
        )
        if item is None:
            item = Artifact(run_id=run_id, path=path)
            session.add(item)
        item.step_id = step_id
        item.mime_type = mime_type
        item.size_bytes = len(data)
        item.sha256 = hashlib.sha256(data).hexdigest()
        session.flush()
        session.refresh(item)
    return item


def list_artifacts(session: Session, run_id: UUID) -> list[Artifact]:
    return list(
        session.scalars(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.path))
    )


def package_run(session: Session, *, run_id: UUID) -> Artifact:
    # Call only after all producer steps have stopped writing to this run.
    with session.begin():
        if session.get(Run, run_id) is None:
            raise LookupError("Run not found")
        items = [a for a in list_artifacts(session, run_id) if a.path != PACKAGE_PATH]
    if sum(a.size_bytes for a in items) > 200 * 1024 * 1024:
        raise ValueError("Package source limit is 200 MiB")
    if not items:
        raise ValueError("No registered files to package")
    target = artifact_path(run_id, PACKAGE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                archive.writestr(item.path, checked_bytes(item))
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return register_artifact(session, run_id=run_id, path=PACKAGE_PATH, mime_type="application/zip")
