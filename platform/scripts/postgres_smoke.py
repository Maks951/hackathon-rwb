"""PostgreSQL checks in a new isolated schema, retained for inspection."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.config import Settings
from app.errors import AppError
from app.integrations.sql_repository import SqlRunRepository
from app.models.project import Project


async def main():
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("PostgreSQL required")
    schema = "rwb_verify_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    os.environ["DATABASE_URL"] = isolated_url.render_as_string(hide_password=False)
    command.upgrade(Config("alembic.ini"), "head")
    isolated = settings.model_copy(update={"database_url": os.environ["DATABASE_URL"]})
    repo = SqlRunRepository(isolated)
    other = SqlRunRepository(isolated)
    try:
        with Session(repo.engine) as session, session.begin():
            project = Project(
                name="PostgreSQL queue smoke",
                requirements="Employee requests with title, description and status",
            )
            session.add(project)
            session.flush()
            project_id = project.id
        key = uuid4()
        created = await repo.create_run(project_id, key)
        assert (await other.create_run(project_id, key)).id == created.id
        try:
            await other.create_run(project_id, uuid4())
        except AppError as exc:
            assert exc.error.code == "conflict"
        else:
            raise AssertionError("Concurrent active run accepted")
        claimed = await asyncio.gather(repo.claim_next(), other.claim_next())
        assert sum(item is not None for item in claimed) == 1
        assert next(item for item in claimed if item is not None).id == created.id
        await repo.finish_run(created.id, "failed", None, datetime.now(UTC))
        assert (await other.get_run(created.id)).status.value == "failed"
        print(
            {
                "ok": True,
                "schema": schema,
                "runId": str(created.id),
                "checks": [
                    "migrations",
                    "persistence",
                    "idempotency",
                    "active-run-conflict",
                    "concurrent-claim",
                ],
                "note": "Test schema retained. This is NOT a generation run.",
            }
        )
    finally:
        repo.close()
        other.close()
        admin.dispose()


if __name__ == "__main__":
    asyncio.run(main())
