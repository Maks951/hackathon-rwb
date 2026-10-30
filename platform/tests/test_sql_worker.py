"""Integration checks: real SQL persistence, scripted model/runner only."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.api.application import create_app
from app.errors import AppError
from app.integrations.sql_repository import SqlRunRepository
from app.models.artifact import Artifact
from app.models.project import Project
from app.models.step import Step
from app.schemas.runs import RunStatus, ValidationStatus
from app.services.storage import Storage
from app.worker import Worker


@pytest.fixture
def sql_runtime(settings, runtime, tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/worker.db"
    monkeypatch.setenv("DATABASE_URL", url)

    # Legacy migrations contain literal PostgreSQL now(); emulate this in SQLite only.
    def sqlite_now(connection, record):
        if type(connection).__module__ == "sqlite3":
            connection.create_function("now", 0, lambda: datetime.now(UTC).isoformat())
            connection.execute("PRAGMA foreign_keys=ON")

    event.listen(Engine, "connect", sqlite_now)
    command.upgrade(Config("alembic.ini"), "head")
    configured = settings.model_copy(update={"database_url": url})
    repo = SqlRunRepository(configured)
    runtime.repository = repo
    engine = create_engine(url)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        project = Project(
            name="SQL demo", requirements="Generate a catalog with products and prices"
        )
        session.add(project)
        session.flush()
        project_id = project.id
    yield configured, runtime, factory, project_id
    repo.close()
    engine.dispose()
    event.remove(Engine, "connect", sqlite_now)


async def test_worker_pipeline_persists_steps_calls_events_and_package(sql_runtime):
    settings, runtime, factory, project_id = sql_runtime
    key = uuid4()
    queued = await runtime.repository.create_run(project_id, key)
    assert queued.status == RunStatus.QUEUED
    assert (await runtime.repository.create_run(project_id, key)).id == queued.id
    assert await Worker(runtime, settings).run_once()
    # Read using a fresh adapter/engine, not objects retained by the worker.
    reloaded = SqlRunRepository(settings)
    try:
        run = await reloaded.get_run(queued.id)
        assert run.status == RunStatus.SUCCEEDED, run.error
        assert run.validation_status == ValidationStatus.PASSED
        steps = await reloaded.list_steps(run.id)
        assert any(s.key == "analyze" and s.status == "succeeded" for s in steps)
        events = await reloaded.list_events(run.id, 0, 1000)
        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
        assert await reloaded.list_events(run.id, events[-1].sequence, 1000) == []
        package = await reloaded.get_package(run.id)
        assert package is not None and Storage(settings).verified_path(package).is_file()
        with factory() as session:
            step = session.scalar(select(Step).where(Step.run_id == run.id, Step.key == "analyze"))
            assert step.metadata_json["calls"][0]["modelId"]
            assert step.input_path and step.output_path and step.finished_at
            artifacts = list(session.scalars(select(Artifact).where(Artifact.run_id == run.id)))
            assert artifacts
            assert any(a.path.startswith("workspaces/") for a in artifacts)
        # Finished runs cannot be resurrected or mutated by a late worker call.
        assert not await reloaded.heartbeat(run.id, datetime.now(UTC))
        with pytest.raises(AppError):
            await reloaded.add_event(run.id, "late", "must not persist")
        assert (await reloaded.create_run(project_id, key)).id == run.id
    finally:
        reloaded.close()


async def test_worker_failure_keeps_raw_response_and_error(sql_runtime):
    settings, runtime, factory, project_id = sql_runtime
    from app.ports import GenerationResponse

    runtime.generation.analyze_responses = [
        GenerationResponse("not-json", "model", "v1"),
        GenerationResponse("not-json", "model", "v1"),
    ]
    run = await runtime.repository.create_run(project_id, uuid4())
    await Worker(runtime, settings).run_once()
    failed = await runtime.repository.get_run(run.id)
    assert failed.status == RunStatus.FAILED
    assert failed.error.code == "invalid_model_output"
    assert await runtime.repository.get_package(run.id) is None
    with factory() as session:
        step = session.scalar(select(Step).where(Step.run_id == run.id))
        assert step.status == "failed" and len(step.metadata_json["calls"]) == 2
        assert len(list(session.scalars(select(Artifact).where(Artifact.step_id == step.id)))) == 2


async def test_stale_recovery_rejects_late_completion(sql_runtime):
    settings, runtime, factory, project_id = sql_runtime
    repo = runtime.repository
    queued = await repo.create_run(project_id, uuid4())
    run = await repo.claim_next()
    now = datetime.now(UTC)
    storage = Storage(settings)
    saved = storage.write_json(f"{run.id}/steps/analyze/001/input.json", {"requirements": "test"})
    step = await repo.start_step(run.id, "analyze", 1, saved.path, now)
    await repo.heartbeat(run.id, now - timedelta(minutes=10))
    assert await repo.fail_stale(now - timedelta(minutes=5), now) == 1
    recovered = await repo.get_run(queued.id)
    assert recovered.status == RunStatus.FAILED and recovered.error.code == "worker_interrupted"
    steps = await repo.list_steps(run.id)
    assert steps[0].status == "failed" and steps[0].error.code == "worker_interrupted"
    with pytest.raises(AppError):
        await repo.complete_step(step.id, saved.path, {}, [saved], now)
    assert not await repo.heartbeat(run.id, now)


async def test_api_uses_sql_runtime_and_persists_conflicts(sql_runtime):
    settings, runtime, factory, project_id = sql_runtime
    from app.api.artifacts import router

    runtime.routers = (router,)
    app = create_app(settings, runtime)
    with TestClient(app) as client:
        key = str(uuid4())
        response = client.post(
            f"/api/v1/projects/{project_id}/runs", json={}, headers={"Idempotency-Key": key}
        )
        assert response.status_code == 202
        run_id = response.json()["id"]
        assert client.get("/health").status_code == 200
        again = client.post(
            f"/api/v1/projects/{project_id}/runs", json={}, headers={"Idempotency-Key": key}
        )
        assert again.json()["id"] == run_id
        conflict = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert conflict.status_code == 409
        assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "queued"
        assert client.get(f"/api/v1/runs/{run_id}/download").status_code == 409
