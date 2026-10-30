import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.db import get_session
from app.models.project import Project
from app.project_demo import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    # TEST_DATABASE_URL must point to a disposable database; downgrade deletes projects.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/projects.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    engine = create_engine(url)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()
    command.downgrade(config, "base")
    engine = create_engine(url)
    assert "projects" not in inspect(engine).get_table_names()
    engine.dispose()


def client_for(factory):
    def session_dependency():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    return TestClient(app)


def test_persistence_and_contract(database):
    payload = {"name": "Demo", "requirements": "Build a product catalog with prices"}
    try:
        with client_for(database) as client:
            response = client.post("/api/v1/projects", json=payload)
            assert response.status_code == 201
            project = response.json()
            assert set(project) == {"id", "name", "requirements", "createdAt"}
            assert project["createdAt"].endswith("Z")
        # New app/client and DB session read the committed project.
        with client_for(database) as client:
            assert client.get(f"/api/v1/projects/{project['id']}").json() == project
            assert client.get("/api/v1/projects").json() == {"items": [project]}
            missing = client.get(f"/api/v1/projects/{uuid4()}")
            assert missing.status_code == 404
            assert missing.json()["code"] == "not_found"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "field,value",
    [("name", ""), ("name", "x" * 121), ("requirements", "x" * 19), ("requirements", "x" * 50001)],
)
def test_input_limits(database, field, value):
    payload = {"name": "Demo", "requirements": "x" * 20, field: value}
    try:
        with client_for(database) as client:
            response = client.post("/api/v1/projects", json=payload)
            assert response.status_code == 400
            assert response.json()["code"] == "invalid_input"
            assert client.get("/api/v1/projects").json() == {"items": []}
    finally:
        app.dependency_overrides.clear()


def test_database_constraint_rollback(database):
    with database() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(Project(name="valid", requirements="x" * 20))
                session.add(Project(name="invalid", requirements="short"))
        assert session.query(Project).count() == 0
