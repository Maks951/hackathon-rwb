import pytest

from app.config import Settings
from app.ports import Runtime
from tests.fakes import MemoryRepository, ScriptedGeneration, ScriptedValidator


@pytest.fixture
def settings(tmp_path):
    templates = tmp_path / "templates"
    # Deliberate test-only stand-ins for the other owners' templates.
    for name in ("dotnet-api", "angular-admin", "angular-pwa", "postgres"):
        folder = templates / name
        folder.mkdir(parents=True)
        (folder / "README.md").write_text("test-only template")
    return Settings(_env_file=None, generated_root=tmp_path / "generated", templates_root=templates)


@pytest.fixture
def runtime():
    return Runtime(MemoryRepository(), ScriptedGeneration(), ScriptedValidator())
