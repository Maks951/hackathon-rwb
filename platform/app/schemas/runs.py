from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiDto(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
        extra="forbid",
    )


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class DeploymentStatus(StrEnum):
    PENDING = "pending"
    SKIPPED = "skipped"
    DEPLOYED = "deployed"
    FAILED = "failed"


class ErrorDto(ApiDto):
    code: str
    message: str
    details: dict[str, str] | None = None


class RunDto(ApiDto):
    id: UUID
    project_id: UUID
    status: RunStatus
    current_step: str | None
    error: ErrorDto | None
    repository_url: str | None
    preview_url: str | None
    created_at: datetime
    finished_at: datetime | None


class StepDto(ApiDto):
    id: UUID
    key: str
    attempt: int = Field(ge=1)
    status: StepStatus
    error: ErrorDto | None


class RunDetailsDto(RunDto):
    steps: list[StepDto]
    validation_status: ValidationStatus
    deployment_status: DeploymentStatus


class CreateRunDto(ApiDto):
    """P0 takes no overrides: requirements are snapshotted by the repository."""


class EventDto(ApiDto):
    id: UUID
    sequence: int = Field(ge=1)
    type: str
    message: str
    created_at: datetime


class EventsDto(ApiDto):
    items: list[EventDto]
    next_sequence: int = Field(ge=0)


class HealthDto(ApiDto):
    status: Literal["ok", "not_ready"]


# Compatibility names for Roman's local scripts.
RunRead = RunDto
RunDetails = RunDetailsDto
StepRead = StepDto
