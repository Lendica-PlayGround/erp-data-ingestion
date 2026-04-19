"""Runtime configuration for the Phase 2 backend.

All paths are resolved eagerly to absolute paths so tool functions can
apply path-traversal checks without re-resolving on every call.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-4o", alias="PHASE2_MODEL")
    output_dir: Path = Field(default=Path("../output"), alias="PHASE2_OUTPUT_DIR")
    upload_dir: Path = Field(default=Path("./uploads"), alias="PHASE2_UPLOAD_DIR")
    frontend_origin: str = Field(
        default="http://localhost:3000", alias="PHASE2_FRONTEND_ORIGIN"
    )

    @property
    def output_path(self) -> Path:
        path = self.output_dir
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path

    @property
    def upload_path(self) -> Path:
        path = self.upload_dir
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.output_path.mkdir(parents=True, exist_ok=True)
    s.upload_path.mkdir(parents=True, exist_ok=True)
    return s
