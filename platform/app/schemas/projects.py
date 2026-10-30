from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    requirements: str = Field(min_length=20, max_length=50000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID
    name: str
    requirements: str
    created_at: datetime = Field(serialization_alias="createdAt")

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:  # SQLite test adapter; PostgreSQL returns aware timestamps.
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ProjectList(BaseModel):
    items: list[ProjectRead]
