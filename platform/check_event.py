from uuid import UUID

from app.db import get_session_factory
from app.repositories.run_events import append_event

run_id = UUID(input("Вставь ID запуска без кавычек: ").strip())

with get_session_factory()() as session:
    event = append_event(
        session,
        run_id=run_id,
        event_type="manual_check",
        message="Проверка записи событий",
    )
    print("Сохранено событие №", event.sequence)