from dataclasses import asdict
from typing import Any
from urllib.parse import urlsplit

from app.config import Settings
from app.errors import AppError, IntegrationUnavailable
from app.ports import (
    ArtifactRecord,
    GenerationStage,
    RunRecord,
    Runtime,
    ValidationReport,
    ValidationStatus,
    Workspace,
)
from app.schemas.runs import DeploymentStatus
from app.services.documentation import DocumentationPolicy, check_documentation, load_policy
from app.services.steps import StepExecutor, StepResult
from app.services.storage import StageFiles, Storage

CODE_STAGES: tuple[GenerationStage, ...] = (
    "generate_db",
    "generate_backend",
    "generate_web",
    "generate_pwa",
    "generate_tests_docs",
)


class OptionalOperationFailed(AppError):
    pass


def public_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise AppError("invalid_adapter_url", "Адаптер вернул недопустимый URL.")
    if parsed.query or parsed.fragment:
        raise AppError(
            "invalid_adapter_url", "URL результата не должен содержать секреты или параметры."
        )
    return value


def api_contract(spec: dict[str, Any]) -> dict[str, Any]:
    # Full SystemSpec schema and reference validation belong to Vladimir's adapter.
    endpoints = spec.get("endpoints")
    if spec.get("schemaVersion") != 1 or not isinstance(endpoints, list) or not endpoints:
        raise AppError("invalid_api_contract", "SystemSpec не содержит API-контракт.")
    if any(not isinstance(e, dict) or not isinstance(e.get("id"), str) for e in endpoints):
        raise AppError("invalid_api_contract", "API endpoint должен иметь уникальный id.")
    ids = [e["id"] for e in endpoints]
    if len(ids) != len(set(ids)):
        raise AppError("invalid_api_contract", "API endpoint id повторяется.")
    return {"schemaVersion": 1, "endpoints": endpoints}


class Pipeline:
    def __init__(self, runtime: Runtime, settings: Settings):
        if runtime.repository is None:
            raise IntegrationUnavailable("repository")
        if runtime.generation is None:
            raise IntegrationUnavailable("Qwen adapter")
        self.runtime = runtime
        self.settings = settings
        self.repository = runtime.repository
        self.storage = Storage(settings)
        self.steps = StepExecutor(runtime.repository, runtime.generation, self.storage, settings)

    async def run(self, run: RunRecord) -> None:
        policy = load_policy().model_dump(mode="json")
        saved_policy = self.storage.write_json(f"{run.id}/documentation-policy.json", policy)
        documentation = {
            "documentationPolicy": policy,
            "documentationPolicySha256": saved_policy.sha256,
        }
        # Analyze/design can be used independently before colleagues' templates are available.
        snapshot = self.storage.write_json(
            f"{run.id}/requirements.json",
            {
                "requirements": run.requirements_snapshot,
            },
        )
        analyzed_path = await self.steps.generate(
            run.id,
            "analyze",
            1,
            {**self.storage.read_json(snapshot.path), **documentation},
        )
        spec_path = await self.steps.generate(
            run.id,
            "design",
            1,
            {"requirementsSpec": self.storage.read_json(analyzed_path), **documentation},
        )
        spec = self.storage.read_json(spec_path)
        contract = api_contract(spec)
        contract_artifact = self.storage.write_json(f"{run.id}/generated-api.json", contract)

        # Frozen template and spec inputs: repair never edits either one.
        files = self.storage.templates()
        files["generated-api.json"] = self.storage.json_bytes(contract)
        files["requirements-spec.json"] = self.storage.json_bytes(
            self.storage.read_json(analyzed_path)
        )
        files["system-spec.json"] = self.storage.json_bytes(spec)
        files["documentation-policy.json"] = self.storage.json_bytes(policy)
        for stage in CODE_STAGES:
            template_root = {
                "generate_db": "database/",
                "generate_backend": "backend/",
                "generate_web": "admin/",
                "generate_pwa": "pwa/",
                "generate_tests_docs": "backend/tests/",
            }[stage]
            output_path = await self.steps.generate(
                run.id,
                stage,
                1,
                {
                    "systemSpec": self.storage.read_json(spec_path),
                    "generatedApi": self.storage.read_json(contract_artifact.path),
                    "generatedApiSha256": contract_artifact.sha256,
                    "ownedPaths": self.owned_paths(stage),
                    **documentation,
                    "templateContext": [
                        {"path": name, "content": content.decode("utf-8")}
                        for name, content in files.items()
                        if name.startswith(template_root)
                        and name.endswith(
                            (
                                ".cs",
                                ".csproj",
                                ".props",
                                ".json",
                                ".ts",
                                ".html",
                                ".scss",
                                ".css",
                                ".sql",
                                ".md",
                                ".yml",
                            )
                        )
                        and not name.endswith(".lock.json")
                    ],
                },
            )
            stage_files = StageFiles.model_validate(self.storage.read_json(output_path))
            patches = self.storage.validate_files(stage, stage_files)
            if any(name in files for name in patches):
                raise AppError(
                    "file_collision", "Этап пытается перезаписать файл другого этапа или шаблона."
                )
            files.update(patches)
        workspace = self.storage.materialize(run.id, 0, files)

        for repair_cycle in range(3):
            report = await self.validate(run, workspace, repair_cycle + 1)
            if report.passed:
                await self.repository.set_validation(run.id, ValidationStatus.PASSED)
                break
            await self.repository.set_validation(run.id, ValidationStatus.FAILED)
            if repair_cycle == 2:
                raise AppError(
                    "validation_failed", "Проверки не пройдены после двух циклов исправления."
                )
            # Old failed status must not be shown as ready while repair/new validation runs.
            await self.repository.set_validation(run.id, ValidationStatus.PENDING)
            errors = [asdict(check) for check in report.checks]
            repair_path = await self.steps.generate(
                run.id,
                "repair",
                repair_cycle + 1,
                {
                    "systemSpec": self.storage.read_json(spec_path),
                    "generatedApi": self.storage.read_json(contract_artifact.path),
                    "generatedApiSha256": contract_artifact.sha256,
                    "workspaceId": workspace.id,
                    "files": self.repair_inputs(workspace),
                    "validation": errors,
                    **documentation,
                    "constraint": (
                        "Only replace generated files. SystemSpec and dependencies are immutable."
                    ),
                },
            )
            patches = self.storage.validate_files(
                "repair",
                StageFiles.model_validate(self.storage.read_json(repair_path)),
            )
            files = self.storage.workspace_files(workspace)
            files.update(patches)
            # Every attempt is a new tree; every required check runs again against its manifest.
            workspace = self.storage.materialize(run.id, repair_cycle + 1, files)

        async def package_operation() -> StepResult:
            artifact = self.storage.package(
                run.id,
                workspace,
                validation={
                    "passed": report.passed,
                    "checks": [asdict(c) for c in report.checks],
                    "workspaceId": workspace.id,
                    "sourceManifest": [asdict(a) for a in workspace.files],
                    "documentationPolicySha256": saved_policy.sha256,
                },
            )
            return StepResult(asdict(artifact), [*workspace.files, artifact])

        package_path = await self.steps.execute(
            run.id, "package", 1, {"workspaceId": workspace.id}, package_operation
        )
        package = ArtifactRecord(**self.storage.read_json(package_path))
        await self.repository.save_package(run.id, package)

        # Optional external operations cannot turn validation failure into readiness.
        if self.runtime.publisher is not None:

            async def publish_operation() -> StepResult:
                try:
                    url = public_url(await self.runtime.publisher.publish(run.id, package))
                except Exception:
                    raise OptionalOperationFailed(
                        "publish_failed", "Публикация не выполнена."
                    ) from None
                return StepResult({"repositoryUrl": url})

            try:
                published = await self.steps.execute(
                    run.id, "publish", 1, {"packageSha256": package.sha256}, publish_operation
                )
                await self.repository.set_repository_url(
                    run.id,
                    self.storage.read_json(published)["repositoryUrl"],
                )
            except OptionalOperationFailed:
                await self.repository.add_event(
                    run.id, "publish_failed", "Публикация не выполнена."
                )

        if self.runtime.deployer is None:
            await self.repository.set_deployment(run.id, DeploymentStatus.SKIPPED, None)
        else:

            async def deploy_operation() -> StepResult:
                try:
                    url = public_url(await self.runtime.deployer.deploy(run.id, workspace))
                except Exception:
                    raise OptionalOperationFailed(
                        "deployment_failed", "Развёртывание не выполнено."
                    ) from None
                return StepResult({"previewUrl": url})

            try:
                deployed = await self.steps.execute(
                    run.id, "deploy", 1, {"workspaceId": workspace.id}, deploy_operation
                )
                await self.repository.set_deployment(
                    run.id,
                    DeploymentStatus.DEPLOYED,
                    self.storage.read_json(deployed)["previewUrl"],
                )
            except OptionalOperationFailed:
                await self.repository.set_deployment(run.id, DeploymentStatus.FAILED, None)

    async def validate(
        self, run: RunRecord, workspace: Workspace, attempt: int
    ) -> ValidationReport:
        report: ValidationReport | None = None

        async def operation() -> StepResult:
            nonlocal report
            if self.runtime.validator is None:
                raise IntegrationUnavailable("validation runner")
            # Read before and after the runner: neither runner nor repair may mutate old attempts.
            files = self.storage.workspace_files(workspace)
            policy = DocumentationPolicy.model_validate(
                self.storage.read_json(f"{run.id}/documentation-policy.json")
            )
            doc_check = check_documentation(
                files, self.storage.read_json(f"{run.id}/steps/design/001/output.json"), policy
            )
            runner_report = await self.runtime.validator.validate(workspace)
            # This check is ours; a runner-provided same-name check cannot override it.
            report = ValidationReport((*runner_report.checks, doc_check))
            self.storage.workspace_files(workspace)
            if len(report.checks) > 100 or any(len(c.message) > 8192 for c in report.checks):
                raise AppError("invalid_validation_report", "Отчёт runner превышает лимит.")
            error = (
                None
                if report.passed
                else AppError(
                    "validation_failed",
                    "Проверки сгенерированного продукта не пройдены.",
                ).error
            )
            return StepResult(
                {"passed": report.passed, "checks": [asdict(c) for c in report.checks]},
                list(workspace.files),
                error=error,
            )

        await self.steps.execute(
            run.id,
            "validate",
            attempt,
            {
                "workspaceId": workspace.id,
                "manifest": [asdict(a) for a in workspace.files],
            },
            operation,
        )
        assert report is not None
        return report

    def repair_inputs(self, workspace: Workspace) -> list[dict[str, str]]:
        from app.services.storage import allowed_file

        return [
            {"path": name, "content": data.decode("utf-8")}
            for name, data in self.storage.workspace_files(workspace).items()
            if allowed_file("repair", name)
        ]

    @staticmethod
    def owned_paths(stage: GenerationStage) -> list[str]:
        return {
            "generate_db": ["database/generated/*.sql"],
            "generate_backend": ["backend/src/Generated.Api/Generated/**/*.cs"],
            "generate_web": ["admin/src/app/generated/**"],
            "generate_pwa": ["pwa/src/app/generated/**"],
            "generate_tests_docs": [
                "docs/*.md",
                "backend/tests/Generated.Api.Tests/Generated/**/*.cs",
                "admin/src/app/generated/**/*.spec.ts",
                "pwa/src/app/generated/**/*.spec.ts",
            ],
        }.get(stage, [])
