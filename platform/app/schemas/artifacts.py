from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
    id: UUID
    path: str
    mime_type: str
    size_bytes: int
    sha256: str


class ArtifactList(BaseModel):
    items: list[ArtifactRead]
