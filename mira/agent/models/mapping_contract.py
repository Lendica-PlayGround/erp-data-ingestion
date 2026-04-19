"""Mapping contract models (PRD §4.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    midlayer_field: str
    source_field: str
    confidence: float = Field(ge=0.0, le=1.0)
    transforms: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class ObjectMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    midlayer_table: str
    source_entity: str
    fields: list[FieldMapping]
    unmapped_source_fields: list[str] = Field(default_factory=list)
    object_confidence: float = Field(ge=0.0, le=1.0)


class SyncStrategy(BaseModel):
    model_config = ConfigDict(extra="allow")

    initial: str
    delta: dict[str, Any]


class MappingContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping_version: str
    midlayer_schema_version: str
    company_id: str
    source_profile: dict[str, Any]
    objects: list[ObjectMapping]
    sync_strategy: SyncStrategy
    validation_requirements: list[str]
