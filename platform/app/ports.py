"""Integration boundary. No SQL models, prompts, runner or deployment implementation here."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.runs import (
    DeploymentStatus,
    ErrorDto,
    EventDto,
    RunStatus,
    StepDto,
    ValidationStatus,
)


@dataclass(frozen=True)
class RunRecord:
    id: UUID
    project_id: UUID
    requirements_snapshot: str
    status: RunStatus
    created_at: datetime
    current_step: str | None = None
    error: ErrorDto | None = None
    repository_url: str | None = None
    preview_url: str | None = None
    finished_at: datetime | None = None
    validation_status: ValidationStatus = ValidationStatus.PENDING
    deployment_status: DeploymentStatus = DeploymentStatus.PENDING


@dataclass(frozen=True)
class ArtifactRecord:
    path: str  # Relative to generated_root, not a user-supplied filesystem path.
    mime_type: str
    size_bytes: int
    sha256: str


class RunRepository(Protocol):
    """Roman's adapter: every call owns a short transaction (see docs/integration.md)."""

    async def ping(self) -> bool: ...
    async def create_run(self, project_id: UUID, idempotency_key: UUID) -> RunRecord: ...
    async def get_run(self, run_id: UUID) -> RunRecord | None: ...
    async def list_steps(self, run_id: UUID) -> list[StepDto]: ...
    async def list_events(self, run_id: UUID, after: int, limit: int) -> list[EventDto]: ...
    async def get_package(self, run_id: UUID) -> ArtifactRecord | None: ...
    async def claim_next(self) -> RunRecord | None: ...
    async def heartbeat(self, run_id: UUID, now: datetime) -> bool: ...
    async def fail_stale(self, before: datetime, now: datetime) -> int: ...
    async def start_step(
        self, run_id: UUID, key: str, attempt: int, input_path: str, now: datetime
    ) -> StepDto: ...
    async def complete_step(
        self,
        step_id: UUID,
        output_path: str,
        metadata: dict[str, Any],
        artifacts: list[ArtifactRecord],
        now: datetime,
        error: ErrorDto | None = None,
    ) -> None: ...
    async def record_call(
        self,
        run_id: UUID,
        key: str,
        attempt: int,
        metadata: dict[str, Any],
        artifact: ArtifactRecord,
    ) -> None: ...
    async def fail_step(self, step_id: UUID, error: ErrorDto, now: datetime) -> None: ...
    async def add_event(self, run_id: UUID, type: str, message: str) -> None: ...
    async def set_validation(self, run_id: UUID, status: ValidationStatus) -> None: ...
    async def set_deployment(
        self, run_id: UUID, status: DeploymentStatus, preview_url: str | None
    ) -> None: ...
    async def set_repository_url(self, run_id: UUID, url: str) -> None: ...
    async def save_package(self, run_id: UUID, artifact: ArtifactRecord) -> None: ...
    async def finish_run(
        self, run_id: UUID, status: RunStatus, error: ErrorDto | None, now: datetime
    ) -> None: ...


GenerationStage = Literal[
    "analyze",
    "design",
    "generate_db",
    "generate_backend",
    "generate_web",
    "generate_pwa",
    "generate_tests_docs",
    "repair",
]


@dataclass(frozen=True)
class GenerationRequest:
    stage: GenerationStage
    inputs: dict[str, Any]
    json_errors: tuple[str, ...] = ()
    previous_output: str | None = None


@dataclass(frozen=True)
class GenerationResponse:
    content: str
    model_id: str
    prompt_version: str
    finish_reason: str = "stop"
    input_tokens: int | None = None
    output_tokens: int | None = None


class GenerationAdapter(Protocol):
    """Vladimir owns actual Qwen transport, prompts, spec models and reference validation."""

    def output_schema(self, stage: GenerationStage) -> type[BaseModel]: ...
    async def generate(self, request: GenerationRequest) -> GenerationResponse: ...


@dataclass(frozen=True)
class Workspace:
    id: str  # <run UUID>/<attempt>, never an executable command or arbitrary absolute path.
    files: tuple[ArtifactRecord, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str  # Safe and bounded diagnostic, suitable to pass back to the model.


@dataclass(frozen=True)
class ValidationReport:
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        required = {
            "backend_build",
            "backend_tests",
            "admin_build",
            "pwa_build",
            "api_contract",
            "security",
        }
        names = [c.name for c in self.checks]
        return (
            required.issubset(names)
            and len(names) == len(set(names))
            and all(c.passed for c in self.checks)
        )


class ValidationRunner(Protocol):
    """Dmitry's isolated fixed-profile runner. Must bind results to the given manifest."""

    async def validate(self, workspace: Workspace) -> ValidationReport: ...


class Publisher(Protocol):
    async def publish(self, run_id: UUID, package: ArtifactRecord) -> str: ...


class Deployer(Protocol):
    async def deploy(self, run_id: UUID, workspace: Workspace) -> str: ...


@dataclass
class Runtime:
    repository: RunRepository | None = None
    generation: GenerationAdapter | None = None
    validator: ValidationRunner | None = None
    publisher: Publisher | None = None
    deployer: Deployer | None = None
    routers: tuple[APIRouter, ...] = field(default_factory=tuple)
