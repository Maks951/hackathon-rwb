from uuid import uuid4

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.api.application import create_app
from app.ports import Runtime


def test_real_project_router_in_composition_persists_and_preserves_error_dto(
    settings, tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path}/composition.db"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = settings.model_copy(update={"database_url": url})
    app = create_app(settings, Runtime())
    with TestClient(app) as client:
        # A live connection alone is insufficient before migrations.
        assert client.get("/health").status_code == 503
        assert client.get("/api/v1/projects").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health").status_code == 200
        payload = {
            "name": "Requests",
            "requirements": "Manage customer requests and their statuses",
        }
        response = client.post("/api/v1/projects", json=payload)
        assert response.status_code == 201
        project = response.json()
        assert set(project) == {"id", "name", "requirements", "createdAt"}
        assert client.get(f"/api/v1/projects/{uuid4()}").json()["code"] == "not_found"
        assert client.post("/api/v1/projects", json={"name": "short"}).status_code == 400
        assert (
            client.post(
                f"/api/v1/projects/{project['id']}/runs",
                json={},
                headers={"Idempotency-Key": str(uuid4())},
            ).status_code
            == 503
        )
    # Fresh app and engine: successful creation was a real database commit.
    with TestClient(create_app(settings, Runtime())) as client:
        assert client.get("/api/v1/projects").json() == {"items": [project]}
        assert client.get(f"/api/v1/projects/{project['id']}").json() == project


def test_missing_database_is_503_not_internal_error(settings):
    settings = settings.model_copy(update={"database_url": None})
    with TestClient(create_app(settings, Runtime())) as client:
        response = client.get("/api/v1/projects")
        assert response.status_code == 503
        assert response.json()["code"] == "not_ready"


def test_existing_factory_projects_router_is_not_registered_twice(settings):
    import warnings

    from app.api.projects import router

    app = create_app(settings, Runtime(routers=(router,)))
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        schema = app.openapi()
    assert set(schema["paths"]["/api/v1/projects"]) == {"get", "post"}
    assert not any("Duplicate Operation ID" in str(w.message) for w in notices)
