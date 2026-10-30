import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.main import create_app
from app.ports import Runtime
from tests.fakes import queued_run


def test_queue_returns_202_exact_dto_and_never_calls_llm(settings, runtime):
    repo = runtime.repository
    key = str(uuid4())
    with TestClient(create_app(settings, runtime)) as client:
        url = f"/api/v1/projects/{repo.project_id}/runs"
        response = client.post(url, json={}, headers={"Idempotency-Key": key})
        assert response.status_code == 202
        data = response.json()
        assert set(data) == {
            "id",
            "projectId",
            "status",
            "currentStep",
            "error",
            "repositoryUrl",
            "previewUrl",
            "createdAt",
            "finishedAt",
        }
        assert data["status"] == "queued"
        assert data["error"] is None and data["previewUrl"] is None
        assert response.headers["location"] == f"/api/v1/runs/{data['id']}"
        assert not runtime.generation.requests
        duplicate = client.post(url, json={}, headers={"Idempotency-Key": key})
        assert duplicate.json() == data
        detail = client.get(response.headers["location"]).json()
        assert detail["steps"] == []
        assert detail["validationStatus"] == "pending"
        assert detail["deploymentStatus"] == "pending"


@pytest.mark.parametrize(
    "headers,body",
    [
        ({}, {}),
        ({"Idempotency-Key": "wrong"}, {}),
        ({"Idempotency-Key": str(uuid4())}, {"requirements": "x"}),
    ],
)
def test_invalid_creation_is_400(settings, runtime, headers, body):
    with TestClient(create_app(settings, runtime)) as client:
        response = client.post(
            f"/api/v1/projects/{runtime.repository.project_id}/runs", json=body, headers=headers
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_input"
        assert not runtime.repository.runs


def test_not_found_conflict_and_package_readiness(settings, runtime):
    with TestClient(create_app(settings, runtime)) as client:
        assert client.get(f"/api/v1/runs/{uuid4()}").status_code == 404
        url = f"/api/v1/projects/{runtime.repository.project_id}/runs"
        first = client.post(url, json={}, headers={"Idempotency-Key": str(uuid4())}).json()
        assert (
            client.post(url, json={}, headers={"Idempotency-Key": str(uuid4())}).status_code == 409
        )
        assert client.get(f"/api/v1/runs/{first['id']}/download").status_code == 409


def test_events_cursor_and_empty_page(settings, runtime):
    run = asyncio.run(queued_run(runtime.repository))
    for i in range(3):
        asyncio.run(runtime.repository.add_event(run.id, "progress", f"event {i}"))
    settings = settings.model_copy(update={"max_events": 2})
    with TestClient(create_app(settings, runtime)) as client:
        url = f"/api/v1/runs/{run.id}/events"
        page = client.get(url).json()
        assert [e["sequence"] for e in page["items"]] == [1, 2]
        assert page["nextSequence"] == 2
        page = client.get(url, params={"afterSequence": 2}).json()
        assert [e["sequence"] for e in page["items"]] == [3]
        assert client.get(url, params={"afterSequence": 3}).json() == {
            "items": [],
            "nextSequence": 3,
        }
        assert client.get(url, params={"afterSequence": -1}).status_code == 400


def test_no_fake_readiness_without_repository(settings):
    with TestClient(create_app(settings, Runtime())) as client:
        assert client.get("/health").status_code == 503
        assert client.get(f"/api/v1/runs/{uuid4()}").status_code == 503


def test_unexpected_exception_never_exposes_credentials(settings, runtime):
    async def broken(run_id):
        raise RuntimeError("postgresql://user:SECRET@db + provider API_KEY")

    runtime.repository.get_run = broken
    with TestClient(create_app(settings, runtime), raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/runs/{uuid4()}")
        assert response.status_code == 500
        assert "SECRET" not in response.text
        assert response.json()["code"] == "internal_error"


def test_repository_business_error_is_preserved(settings, runtime):
    async def conflict(project_id, idempotency_key):
        raise AppError("idempotency_conflict", "Ключ уже использован.", 409)

    runtime.repository.create_run = conflict
    with TestClient(create_app(settings, runtime)) as client:
        response = client.post(
            f"/api/v1/projects/{uuid4()}/runs", json={}, headers={"Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "idempotency_conflict"
