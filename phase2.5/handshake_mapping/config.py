"""Runtime paths and model selection for Phase 2.5 handshake mapping."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PKG_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PKG_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-4o", alias="PHASE25_MODEL")
    phase2_output_dir: Path = Field(
        default=Path("../phase2/output"), alias="PHASE25_PHASE2_OUTPUT_DIR"
    )
    midlayer_schema_dir: Path = Field(
        default=Path("../midlayer-schema-guide/midlayer/v1"),
        alias="PHASE25_MIDLAYER_SCHEMA_DIR",
    )
    output_file: Path = Field(
        default=Path("./output/handshake_mapping.json"), alias="PHASE25_OUTPUT_FILE"
    )

    @property
    def phase2_output_path(self) -> Path:
        p = self.phase2_output_dir
        if not p.is_absolute():
            p = (_PKG_DIR / p).resolve()
        return p

    @property
    def midlayer_schema_path(self) -> Path:
        p = self.midlayer_schema_dir
        if not p.is_absolute():
            p = (_PKG_DIR / p).resolve()
        return p

    @property
    def output_path(self) -> Path:
        p = self.output_file
        if not p.is_absolute():
            p = (_PKG_DIR / p).resolve()
        return p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
