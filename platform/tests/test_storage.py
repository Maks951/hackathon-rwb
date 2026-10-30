import io
import zipfile
from dataclasses import replace
from uuid import uuid4

import pytest

from app.errors import AppError
from app.services.storage import StageFile, StageFiles, Storage, relative_path
from tests.fakes import BACKEND_FILE


@pytest.mark.parametrize(
    "path",
    [
        "../escape.cs",
        "/tmp/escape.cs",
        "C:/escape.cs",
        "a\\escape.cs",
        "a/../x.cs",
        "a//x.cs",
        "a/./x.cs",
        "a/%2e%2e/x.cs",
        "a/NUL.cs",
        "a/foo./x.cs",
        "",
    ],
)
def test_path_traversal_and_ambiguous_names_are_rejected(path):
    with pytest.raises(AppError):
        relative_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "backend/src/Generated.Api/Generated.Api.csproj",
        "backend/src/Generated.Api/Program.cs",
        "backend/src/Generated.Api/Generated/evil.sh",
        "backend/src/Generated.Api/Generated/package.json",
        "generated-api.json",
        "../escape.cs",
    ],
)
def test_model_cannot_change_dependencies_host_or_contract(settings, path):
    files = StageFiles(schemaVersion=1, files=[StageFile(path=path, content="x")], notes=[])
    with pytest.raises(AppError):
        Storage(settings).validate_files("repair", files)


def test_batch_rejects_duplicates_and_oversize_before_writing(settings):
    storage = Storage(settings)
    duplicate = StageFiles(
        schemaVersion=1,
        files=[
            StageFile(path=BACKEND_FILE, content="one"),
            StageFile(path=BACKEND_FILE.lower(), content="two"),
        ],
        notes=[],
    )
    with pytest.raises(AppError):
        storage.validate_files("generate_backend", duplicate)
    tiny = Storage(settings.model_copy(update={"max_file_bytes": 1}))
    with pytest.raises(AppError, match="output_too_large"):
        tiny.validate_files(
            "generate_backend",
            StageFiles(
                schemaVersion=1, files=[StageFile(path=BACKEND_FILE, content="too large")], notes=[]
            ),
        )
    assert not settings.generated_root.exists()


def test_symlink_escape_is_rejected(settings, tmp_path):
    storage = Storage(settings)
    storage.root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (storage.root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AppError, match="unsafe_path"):
        storage.write("linked/file.txt", b"never", "text/plain")
    assert not (outside / "file.txt").exists()


def test_immutable_writes_and_corruption_detection(settings):
    storage = Storage(settings)
    artifact = storage.write("data/test.json", b"{}", "application/json")
    with pytest.raises(FileExistsError):
        storage.write("data/test.json", b"[]", "application/json")
    storage.path(artifact.path).write_bytes(b"[]")
    with pytest.raises(AppError, match="artifact_corrupt"):
        storage.verified_path(artifact)
    with pytest.raises(AppError):
        storage.verified_path(replace(artifact, path="../outside"))


def test_zip_is_reproducible_and_contains_an_independent_source_tree(settings):
    storage = Storage(settings)
    files = {"backend/Program.cs": b"source", "generated-api.json": b"{}"}
    first_id, second_id = uuid4(), uuid4()
    first = storage.package(first_id, storage.materialize(first_id, 0, files))
    second = storage.package(second_id, storage.materialize(second_id, 0, files))
    assert first.sha256 == second.sha256
    data = storage.verified_path(first).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == ["backend/Program.cs", "generated-api.json"]
        assert archive.read("backend/Program.cs") == b"source"
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())


def test_templates_with_symlinks_are_rejected(settings, tmp_path):
    (settings.templates_root / "dotnet-api" / "linked.cs").symlink_to(tmp_path / "outside")
    with pytest.raises(AppError, match="unsafe_path"):
        Storage(settings).templates()
