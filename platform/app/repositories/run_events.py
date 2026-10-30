from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.run import Run
from app.models.run_event import RunEvent


def append_event(
    session: Session,
    *,
    run_id: UUID,
    event_type: str,
    message: str,
) -> RunEvent:
    with session.begin():
        # Блокируем запуск, чтобы параллельные записи
        # не получили одинаковый номер события.
        existing_id = session.scalar(select(Run.id).where(Run.id == run_id).with_for_update())
        if existing_id is None:
            raise LookupError("Запуск не найден")

        last_sequence = session.scalar(
            select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
        )

        event = RunEvent(
            run_id=run_id,
            sequence=(last_sequence or 0) + 1,
            type=event_type,
            message=message,
        )
        session.add(event)
        session.flush()
        session.refresh(event)

    return event


def list_events(
    session: Session,
    *,
    run_id: UUID,
    after_sequence: int = 0,
) -> list[RunEvent]:
    if after_sequence < 0:
        raise ValueError("after_sequence должен быть >= 0")

    return list(
        session.scalars(
            select(RunEvent)
            .where(
                RunEvent.run_id == run_id,
                RunEvent.sequence > after_sequence,
            )
            .order_by(RunEvent.sequence)
            .limit(100)
        )
    )
