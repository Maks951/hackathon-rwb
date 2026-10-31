import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.errors import AppError
from app.ports import ArtifactRecord, GenerationStage, Workspace


class StageFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    content: str


class StageFiles(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schemaVersion: Literal[1]
    files: list[StageFile]
    notes: list[str]


def relative_path(value: str) -> PurePosixPath:
    parts = value.split("/")
    if (
        not value
        or not re.fullmatch(r"[A-Za-z0-9_./@-]+", value)
        or any(p in ("", ".", "..") for p in parts)
        or any(p.endswith(".") for p in parts)
        or PurePosixPath(value).is_absolute()
        or any(
            p.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
            for p in parts
        )
    ):
        raise AppError("unsafe_path", "Недопустимый путь сгенерированного файла.")
    return PurePosixPath(value)


def allowed_file(stage: GenerationStage, path: str) -> bool:
    if stage == "generate_tests_docs" and path.startswith(("admin/", "pwa/")):
        if not path.endswith(".spec.ts"):
            return False
    rules = {
        "generate_db": [("database/generated/", {".sql"})],
        "generate_backend": [
            ("backend/src/Generated.Api/Generated/", {".cs"}),
            ("backend/tests/Generated.Api.Tests/Generated/", {".cs"}),
        ],
        "generate_web": [("admin/src/app/generated/", {".ts", ".html", ".scss", ".css"})],
        "generate_pwa": [("pwa/src/app/generated/", {".ts", ".html", ".scss", ".css"})],
        "generate_tests_docs": [
            ("docs/", {".md"}),
            ("backend/tests/Generated.Api.Tests/Generated/", {".cs"}),
            ("admin/src/app/generated/", {".ts"}),
            ("pwa/src/app/generated/", {".ts"}),
        ],
    }
    selected = (
        [r for rs in rules.values() for r in rs] if stage == "repair" else rules.get(stage, [])
    )
    return any(
        path.startswith(prefix) and PurePosixPath(path).suffix in suffixes
        for prefix, suffixes in selected
    )


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.generated_root.absolute()

    def path(self, relative: str) -> Path:
        parts = relative_path(relative).parts
        current = self.root
        for ancestor in (current, *current.parents):
            if ancestor.is_symlink():
                raise AppError("unsafe_path", "Каталог артефактов содержит символьную ссылку.")
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise AppError("unsafe_path", "Символьные ссылки в артефактах запрещены.")
        return current

    def write(self, relative: str, data: bytes, mime: str) -> ArtifactRecord:
        if len(data) > self.settings.max_tree_bytes:
            raise AppError("output_too_large", "Превышен лимит размера артефакта.", 413)
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        return ArtifactRecord(relative, mime, len(data), hashlib.sha256(data).hexdigest())

    def write_json(self, relative: str, value: Any) -> ArtifactRecord:
        return self.write(relative, self.json_bytes(value), "application/json")

    @staticmethod
    def json_bytes(value: Any) -> bytes:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

    def read_json(self, relative: str) -> Any:
        path = self.path(relative)
        if path.stat().st_size > self.settings.max_response_bytes:
            raise AppError("output_too_large", "Превышен лимит размера JSON.", 413)
        return json.loads(path.read_text(encoding="utf-8"))

    def verified_path(self, artifact: ArtifactRecord) -> Path:
        path = self.path(artifact.path)
        if not path.is_file() or path.stat().st_size != artifact.size_bytes:
            raise AppError("artifact_corrupt", "Артефакт отсутствует или повреждён.", 503)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != artifact.sha256:
            raise AppError("artifact_corrupt", "Контрольная сумма артефакта не совпадает.", 503)
        return path

    def validate_files(self, stage: GenerationStage, files: StageFiles) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        names: set[str] = set()
        for file in files.files:
            name = str(relative_path(file.path))
            if name.casefold() in names or not allowed_file(stage, name):
                raise AppError("unsafe_file", "Путь файла повторяется или не разрешён для этапа.")
            data = file.content.encode("utf-8")
            if len(data) > self.settings.max_file_bytes:
                raise AppError("output_too_large", "Превышен лимит размера файла.", 413)
            result[name] = data
            names.add(name.casefold())
        self.check_tree(result)
        if not result:
            raise AppError("empty_generation", "Модель не вернула файлы этапа.")
        return result

    def check_tree(self, files: dict[str, bytes]) -> None:
        if (
            len(files) > self.settings.max_files
            or sum(map(len, files.values())) > self.settings.max_tree_bytes
            or any(len(data) > self.settings.max_file_bytes for data in files.values())
        ):
            raise AppError("output_too_large", "Превышен лимит дерева файлов.", 413)
        names = {name.casefold() for name in files}
        if len(names) != len(files):
            raise AppError("unsafe_file", "Имена файлов конфликтуют без учёта регистра.")
        for name in files:
            if any(
                str(p).casefold() in names for p in PurePosixPath(name).parents if str(p) != "."
            ):
                raise AppError("unsafe_file", "Путь используется и как файл, и как каталог.")

    def templates(self) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        for template, target in {
            "dotnet-api": "backend",
            "angular-admin": "admin",
            "angular-pwa": "pwa",
            "postgres": "database",
            "product": "",
        }.items():
            root = self.settings.templates_root.absolute() / template
            if template == "product" and not root.is_dir():
                continue  # Older test fixtures may omit deployment assets.
            if not root.is_dir():
                raise AppError("template_missing", f"Не подключён шаблон: {template}.", 503)
            if any(p.is_symlink() for p in (root, *root.parents)):
                raise AppError("unsafe_path", "Символьные ссылки в шаблонах запрещены.")
            for source in sorted(root.rglob("*")):
                if source.is_symlink():
                    raise AppError("unsafe_path", "Символьные ссылки в шаблонах запрещены.")
                relative = source.relative_to(root)
                if any(
                    p in {"bin", "obj", "node_modules", ".git", "TestResults"}
                    for p in relative.parts
                ):
                    continue
                if source.is_file():
                    name = str(
                        relative_path(
                            f"{target}/{relative.as_posix()}" if target else relative.as_posix()
                        )
                    )
                    if source.stat().st_size > self.settings.max_file_bytes:
                        raise AppError("output_too_large", "Превышен лимит файла шаблона.", 413)
                    result[name] = source.read_bytes()
        self.check_tree(result)
        return result

    def materialize(
        self,
        run_id: UUID,
        attempt: int,
        files: dict[str, bytes],
    ) -> Workspace:
        self.check_tree(files)
        prefix = f"{run_id}/workspaces/{attempt:03d}"
        # A workspace is never reused or edited, including on worker restart.
        self.path(prefix).mkdir(parents=True, exist_ok=False)
        artifacts = tuple(
            self.write(f"{prefix}/{name}", data, "text/plain")
            for name, data in sorted(files.items())
        )
        return Workspace(f"{run_id}/{attempt:03d}", artifacts)

    def workspace_files(self, workspace: Workspace) -> dict[str, bytes]:
        run_id, attempt = workspace.id.split("/")
        prefix = f"{UUID(run_id)}/workspaces/{int(attempt):03d}/"
        files = {}
        if len({a.path for a in workspace.files}) != len(workspace.files):
            raise AppError("artifact_corrupt", "Файлы manifest повторяются.")
        self.check_tree({a.path: b"" for a in workspace.files})
        actual = set()
        for path in self.path(prefix.rstrip("/")).rglob("*"):
            if path.is_symlink():
                raise AppError("artifact_corrupt", "Workspace содержит символьную ссылку.")
            if path.is_file():
                actual.add(path.relative_to(self.root).as_posix())
        if actual != {a.path for a in workspace.files}:
            raise AppError("artifact_corrupt", "Workspace не совпадает с manifest.")
        for artifact in workspace.files:
            if not artifact.path.startswith(prefix):
                raise AppError("unsafe_path", "Файл не относится к workspace.")
            name = artifact.path.removeprefix(prefix)
            relative_path(name)
            files[name] = self.verified_path(artifact).read_bytes()
        self.check_tree(files)
        return files

    def package(
        self, run_id: UUID, workspace: Workspace, validation: dict | None = None
    ) -> ArtifactRecord:
        files = self.workspace_files(workspace)
        if validation is not None:
            if "reports/validation.json" in files:
                raise AppError("file_collision", "Отчёт проверок должен формировать pipeline.")
            files["reports/validation.json"] = self.json_bytes(validation)
        self.check_tree(files)
        stream = io.BytesIO()
        # Fixed timestamps, permissions, order and compression make the ZIP reproducible.
        with zipfile.ZipFile(
            stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        return self.write(f"{run_id}/package/product.zip", stream.getvalue(), "application/zip")
