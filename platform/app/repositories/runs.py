from uuid import UUID
from sqlalchemy import func, update
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import json
from datetime import datetime, timedelta, timezone
from app.models.project import Project
from app.models.run import Run


class ProjectNotFound(Exception):
    pass


class RunConflict(Exception):
    pass


def create_run_with_snapshot(
    session: Session,
    *,
    project_id: UUID,
    idempotency_key: UUID,
) -> Run:
    try:
        with session.begin():
            # Блокируем проект до commit, чтобы два запроса
            # не создали одновременно два активных запуска.
            project = session.scalar(
                select(Project)
                .where(Project.id == project_id)
                .with_for_update()
            )
            if project is None:
                raise ProjectNotFound()

            existing = session.scalar(
                select(Run).where(
                    Run.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                if existing.project_id != project_id:
                    raise RunConflict(
                        "Этот ключ уже используется другим проектом"
                    )
                return existing

            active = session.scalar(
                select(Run).where(
                    Run.project_id == project_id,
                    Run.status.in_(["queued", "running"]),
                )
            )
            if active is not None:
                raise RunConflict(
                    "У проекта уже есть активный запуск"
                )

            run = Run(
                project_id=project_id,
                idempotency_key=idempotency_key,
                requirements_snapshot=project.requirements,
            )
            session.add(run)
            session.flush()
            session.refresh(run)

        return run

    except IntegrityError:
        # Возможна гонка одного ключа между разными проектами.
        # Предыдущая транзакция уже отменена.
        with session.begin():
            existing = session.scalar(
                select(Run).where(
                    Run.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                if existing.project_id == project_id:
                    return existing
                raise RunConflict(
                    "Этот ключ уже используется другим проектом"
                )
        raise
    
def get_run(session: Session, run_id: UUID) -> Run | None:
    return session.get(Run, run_id)
def claim_next_run(session: Session) -> Run | None:
    with session.begin():
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
        run.heartbeat_at = func.now()

        session.flush()
        session.refresh(run)

    # Транзакция уже завершена — можно вызывать Qwen.
    return run


def heartbeat(session: Session, run_id: UUID) -> bool:
    with session.begin():
        result = session.execute(
            update(Run)
            .where(
                Run.id == run_id,
                Run.status == "running",
            )
            .values(heartbeat_at=func.now())
        )

    return result.rowcount == 1
def fail_stale_runs(
    session: Session,
    *,
    timeout_seconds: int = 300,
) -> list[UUID]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds должен быть больше нуля")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=timeout_seconds)

    with session.begin():
        result = session.execute(
            update(Run)
            .where(
                Run.status == "running",
                func.coalesce(
                    Run.heartbeat_at,
                    Run.created_at,
                ) < cutoff,
            )
            .values(
                status="failed",
                finished_at=now,
                error=json.dumps(
                    {
                        "code": "worker_interrupted",
                        "message": "Worker перестал отправлять heartbeat",
                    },
                    ensure_ascii=False,
                ),
            )
            .returning(Run.id)
        )
        failed_ids = list(result.scalars())

    return failed_ids