from pathlib import Path

import yaml


def test_compose_connects_migrations_health_and_separate_worker_without_docker_socket():
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "compose.backend.yaml").read_text())
    services = config["services"]
    assert services["api"]["build"]["dockerfile"] == "platform/Dockerfile"
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert services["migrate"]["command"] == ["python", "-m", "alembic", "upgrade", "head"]
    assert services["worker"]["command"] == ["python", "-m", "app.worker"]
    assert services["worker"]["profiles"] == ["pipeline"]
    assert services["api"]["volumes"] == services["worker"]["volumes"]
    assert "ports" not in services["database"]
    for name in ("api", "worker", "migrate"):
        assert "docker.sock" not in str(services[name].get("volumes", []))
    assert services["runner"]["profiles"] == ["pipeline"]
    assert "env_file" not in services["runner"]
    assert "ports" not in services["runner"]
