from datetime import datetime, timezone
import hashlib
import io
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from test_projects import database, client_for
from app.db import get_session
from app.models.project import Project
from app.models.run import Run
from app.project_demo import app
from app.repositories.artifacts import (
    UnsafeArtifactPath, artifact_path, package_run, register_artifact,
)


def new_run(factory):
    with factory() as session, session.begin():
        p = Project(name='Demo', requirements='x' * 20)
        session.add(p)
        session.flush()
        run = Run(project_id=p.id, idempotency_key=uuid4(), requirements_snapshot=p.requirements, created_at=datetime.now(timezone.utc))
        session.add(run)
        session.flush()
        return run.id


def test_artifact_roundtrip(database, tmp_path, monkeypatch):
    monkeypatch.setenv('GENERATED_ROOT', str(tmp_path / 'generated'))
    run_id = new_run(database)
    path = artifact_path(run_id, 'src/example.html')
    path.parent.mkdir(parents=True)
    content = b'<h1>Example</h1>'
    path.write_bytes(content)
    with database() as session:
        item = register_artifact(session, run_id=run_id, path='src/example.html', mime_type='text/html')
    assert item.sha256 == hashlib.sha256(content).hexdigest()
    with database() as session:
        repeated = register_artifact(session, run_id=run_id, path='src/example.html', mime_type='text/html')
    assert repeated.id == item.id
    try:
        with client_for(database) as client:
            assert client.get(f'/api/v1/runs/{run_id}/download').status_code == 409
            details = client.get(f'/api/v1/runs/{run_id}').json()
            assert details['steps'] == []
            assert details['validationStatus'] == 'pending'
            result = client.get(f'/api/v1/artifacts/{item.id}/content')
            assert result.content == content
            assert result.headers['content-type'].startswith('text/plain')
            assert result.headers['x-content-type-options'] == 'nosniff'
        with database() as session:
            package_run(session, run_id=run_id)
        with client_for(database) as client:
            response = client.get(f'/api/v1/runs/{run_id}/download')
            assert response.status_code == 200
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert archive.namelist() == ['src/example.html']
                assert archive.read('src/example.html') == content
            assert len(client.get(f'/api/v1/runs/{run_id}/artifacts').json()['items']) == 2
            path.write_bytes(b'x' * (1024 * 1024 + 1))
            assert client.get(f'/api/v1/artifacts/{item.id}/content').status_code == 413
            path.write_text('changed')
            assert client.get(f'/api/v1/artifacts/{item.id}/content').status_code == 409
            assert client.get(f'/api/v1/runs/{uuid4()}/download').status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', 'C:/secret', 'a\\secret', 'a/../../b', 'a//b', ''])
def test_unsafe_path(path):
    with pytest.raises(UnsafeArtifactPath):
        artifact_path(uuid4(), path)


def test_symlink_escape(tmp_path, monkeypatch):
    monkeypatch.setenv('GENERATED_ROOT', str(tmp_path / 'generated'))
    run_id = uuid4()
    directory = artifact_path(run_id, 'safe').parent
    directory.mkdir(parents=True)
    (directory / 'escape').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(UnsafeArtifactPath):
        artifact_path(run_id, 'escape/file.txt')
