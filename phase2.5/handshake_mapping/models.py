"""Pydantic models for handshake mapping output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ColumnHandshake(BaseModel):
    """Mapping for one Phase 2 column."""

    phase2_column: str
    midlayer_columns: list[str] = Field(
        ...,
        description='Canonical mid-layer column name(s), or the literal "other".',
    )
    processing_steps: list[str] = Field(
        default_factory=list,
        description="Type conversions, parsing, and format normalization.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("midlayer_columns")
    @classmethod
    def other_is_exclusive(cls, v: list[str]) -> list[str]:
        if "other" in v and len(v) > 1:
            raise ValueError('"other" must be the sole entry when used')
        return v


class TableHandshake(BaseModel):
    """All column mappings for one Phase 2 table."""

    phase2_table: str
    midlayer_table: Literal["invoices", "customers", "contacts"]
    routing_note: str = ""
    columns: list[ColumnHandshake]


class HandshakeRun(BaseModel):
    """Full run artifact written to disk."""

    generated_at: str
    phase2_output_dir: str
    midlayer_schema_dir: str
    model: str
    tables: list[TableHandshake]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
