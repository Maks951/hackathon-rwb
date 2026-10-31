import base64
from dataclasses import asdict
from uuid import uuid4

import httpx
import pytest

from app.errors import AppError
from app.integrations.validation_runner import HttpValidationRunner
from app.runner.protocol import CHECKS, digest_manifest, unpack
from app.services.storage import Storage


def request_for(settings):
    storage = Storage(settings)
    workspace = storage.materialize(uuid4(), 0, {"docs/test.md": b"test"})
    manifest = [asdict(a) for a in workspace.files]
    return workspace, dict(
        workspaceId=workspace.id,
        manifest=manifest,
        manifestSha256=digest_manifest(manifest),
        files={"docs/test.md": base64.b64encode(b"test").decode()},
    )


def test_protocol_rejects_corruption_foreign_duplicate_and_extra_files(settings):
    _, payload = request_for(settings)
    assert unpack(payload) == {"docs/test.md": b"test"}
    payload["files"]["docs/test.md"] = base64.b64encode(b"evil").decode()
    with pytest.raises(ValueError):
        unpack(payload)
    payload["files"]["docs/test.md"] = base64.b64encode(b"test").decode()
    payload["manifest"].append(payload["manifest"][0])
    payload["manifestSha256"] = digest_manifest(payload["manifest"])
    with pytest.raises(ValueError):
        unpack(payload)
    payload["manifest"] = payload["manifest"][:1]
    payload["manifest"][0]["path"] = str(uuid4()) + "/workspaces/000/docs/test.md"
    payload["manifestSha256"] = digest_manifest(payload["manifest"])
    with pytest.raises(ValueError):
        unpack(payload)


@pytest.mark.parametrize("fault", ["digest", "missing", "duplicate", "boolean", "oversize"])
async def test_adapter_rejects_unbound_or_incomplete_reports(settings, fault):
    workspace, payload = request_for(settings)
    report = {k: payload[k] for k in ("workspaceId", "manifestSha256")}
    report["checks"] = [dict(name=n, passed=True, message="actual check") for n in CHECKS]
    if fault == "digest":
        report["manifestSha256"] = "wrong"
    if fault == "missing":
        report["checks"].pop()
    if fault == "duplicate":
        report["checks"][0]["name"] = "security"
    if fault == "boolean":
        report["checks"][0]["passed"] = "true"
    if fault == "oversize":
        report["checks"][0]["message"] = "x" * 70000
    configured = settings.model_copy(update={"runner_url": "http://runner:8090"})
    from pydantic import SecretStr

    configured.runner_token = SecretStr("test-token-" * 4)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=report))
    ) as client:
        with pytest.raises(AppError, match="runner_unavailable"):
            await HttpValidationRunner(configured, client=client).validate(workspace)


def test_sandbox_command_has_no_host_mounts_or_secrets(monkeypatch):
    from app.runner import server

    recorded = []

    def reject(command, **kwargs):
        recorded.extend(command)
        raise OSError("no Docker in unit test")

    monkeypatch.setattr(server.subprocess, "Popen", reject)
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: None)
    assert all(not c["passed"] for c in server.run_container({}))
    assert "--network" in recorded and "none" in recorded
    assert "--read-only" in recorded and "--cap-drop" in recorded
    assert "--volume" not in recorded and "-v" not in recorded and "-e" not in recorded
    assert "docker.sock" not in " ".join(recorded)


def test_runtime_templates_produce_deployable_layout():
    from pathlib import Path

    from app.config import Settings
    from app.runner import sandbox

    files = Storage(
        Settings(_env_file=None, templates_root=Path(__file__).resolve().parents[2] / "templates")
    ).templates()
    for name in [
        "compose.yaml",
        "backend/Dockerfile",
        "admin/Dockerfile",
        "pwa/Dockerfile",
        "database/Dockerfile",
        "README.md",
    ]:
        assert name in files
    # Test the real security implementation against current immutable templates.

    class TrustedStorage:
        def __init__(self, settings):
            pass

        def templates(self):
            return files

    from unittest.mock import patch

    with patch.object(sandbox, "Storage", TrustedStorage):
        assert sandbox.security(dict(files))[0]
        changed = dict(files)
        changed["backend/Dockerfile"] = b"bad"
        assert not sandbox.security(changed)[0]
        changed = dict(files)
        changed["backend/src/Generated.Api/Generated/Evil.cs"] = b'Process.Start("sh");'
        assert not sandbox.security(changed)[0]


def test_trx_requires_actual_passing_tests(tmp_path):
    from app.runner.sandbox import trx_passed

    path = tmp_path / "result.trx"
    for total, passed, expected in [(0, 0, False), (3, 2, False), (3, 3, True)]:
        path.write_text(
            f'<TestRun><ResultSummary><Counters total="{total}" passed="{passed}"/>'
            "</ResultSummary></TestRun>"
        )
        assert trx_passed(path) is expected
