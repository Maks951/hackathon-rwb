"""Strict, versioned domain contracts returned by the Qwen generation adapter."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class ActorSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class FieldSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    type: Literal["string", "integer", "number", "boolean", "date", "datetime", "uuid", "enum", "json", "geojson"]
    nullable: bool = False
    required: bool = True
    enumValues: list[str] = Field(default_factory=list, max_length=100)
    reference: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_enum(self):
        if self.type == "enum" and not self.enumValues:
            raise ValueError("enum fields must declare enumValues")
        if self.type != "enum" and self.enumValues:
            raise ValueError("enumValues are only valid for enum fields")
        return self


class EntitySpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1500)
    fields: list[FieldSpec] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_fields(self):
        ids = [item.id for item in self.fields]
        names = [item.name.casefold() for item in self.fields]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("entity field ids and names must be unique")
        return self


class RuleSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=1, max_length=2000)
    entityRefs: list[str] = Field(default_factory=list, max_length=100)


class AcceptanceCriterion(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=1, max_length=2000)
    verifies: list[str] = Field(default_factory=list, max_length=100)


class RequirementsSpec(StrictModel):
    schemaVersion: Literal[1]
    title: str = Field(min_length=1, max_length=200)
    actors: list[ActorSpec] = Field(default_factory=list, max_length=50)
    entities: list[EntitySpec] = Field(default_factory=list, max_length=100)
    rules: list[RuleSpec] = Field(default_factory=list, max_length=200)
    acceptanceCriteria: list[AcceptanceCriterion] = Field(default_factory=list, max_length=200)
    assumptions: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_references_and_ids(self):
        groups = [self.actors, self.entities, self.rules, self.acceptanceCriteria]
        for group in groups:
            ids = [item.id for item in group]
            if len(ids) != len(set(ids)):
                raise ValueError("ids must be unique within each collection")
        entity_ids = {item.id for item in self.entities}
        for rule in self.rules:
            if not set(rule.entityRefs).issubset(entity_ids):
                raise ValueError(f"rule {rule.id} references an unknown entity")
        known = entity_ids | {item.id for item in self.rules}
        for criterion in self.acceptanceCriteria:
            if not set(criterion.verifies).issubset(known):
                raise ValueError(f"acceptance criterion {criterion.id} has an unknown reference")
        return self


class EndpointSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=500)
    entityRefs: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or ".." in value or "?" in value or "#" in value:
            raise ValueError("endpoint path must be a safe absolute API path")
        return value


class PageSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    entityRefs: list[str] = Field(default_factory=list, max_length=50)
    endpointRefs: list[str] = Field(default_factory=list, max_length=50)


class EventSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    entityRefs: list[str] = Field(default_factory=list, max_length=50)


class AcceptanceTestSpec(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=1, max_length=1500)
    entityRefs: list[str] = Field(default_factory=list, max_length=50)
    endpointRefs: list[str] = Field(default_factory=list, max_length=50)
    pageRefs: list[str] = Field(default_factory=list, max_length=50)


class SystemSpec(StrictModel):
    schemaVersion: Literal[1]
    entities: list[EntitySpec] = Field(default_factory=list, max_length=100)
    endpoints: list[EndpointSpec] = Field(min_length=1, max_length=300)
    pages: list[PageSpec] = Field(default_factory=list, max_length=100)
    events: list[EventSpec] = Field(default_factory=list, max_length=200)
    acceptanceTests: list[AcceptanceTestSpec] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_ids_and_references(self):
        collections = [self.entities, self.endpoints, self.pages, self.events, self.acceptanceTests]
        for group in collections:
            ids = [item.id for item in group]
            if len(ids) != len(set(ids)):
                raise ValueError("ids must be unique within each collection")
        entity_ids = {item.id for item in self.entities}
        endpoint_ids = {item.id for item in self.endpoints}
        page_ids = {item.id for item in self.pages}
        for endpoint in self.endpoints:
            if not set(endpoint.entityRefs).issubset(entity_ids):
                raise ValueError(f"endpoint {endpoint.id} references an unknown entity")
        for page in self.pages:
            if not set(page.entityRefs).issubset(entity_ids):
                raise ValueError(f"page {page.id} references an unknown entity")
            if not set(page.endpointRefs).issubset(endpoint_ids):
                raise ValueError(f"page {page.id} references an unknown endpoint")
        for event in self.events:
            if not set(event.entityRefs).issubset(entity_ids):
                raise ValueError(f"event {event.id} references an unknown entity")
        for test in self.acceptanceTests:
            if not set(test.entityRefs).issubset(entity_ids):
                raise ValueError(f"test {test.id} references an unknown entity")
            if not set(test.endpointRefs).issubset(endpoint_ids):
                raise ValueError(f"test {test.id} references an unknown endpoint")
            if not set(test.pageRefs).issubset(page_ids):
                raise ValueError(f"test {test.id} references an unknown page")
        return self
