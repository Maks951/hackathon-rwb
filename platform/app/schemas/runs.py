from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class RunRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    id: UUID
    project_id: UUID
    status: str
    current_step: str | None
    error: str | None
    repository_url: str | None
    preview_url: str | None
    created_at: datetime
    finished_at: datetime | None