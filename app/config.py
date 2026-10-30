"""Application settings loaded from the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Gemini Embedding 2 recommends 768, 1536, or 3072.
# 768 stays under pgvector's 2000-dimension index limit.
EMBEDDING_DIMENSIONS = 768
EMBEDDING_MODEL = "gemini-embedding-2"


def parse_user_ids(raw: str) -> frozenset[int]:
    """Parse a comma-separated list of Telegram user ids."""
    ids: list[int] = []
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        if not piece.isdigit():
            raise ValueError(
                f"TELEGRAM_ALLOWED_USER_IDS contains a non-numeric id: {piece}"
            )
        ids.append(int(piece))
    return frozenset(ids)


def seed_path() -> Path:
    """Locate the profile seed from the repo root or the process working directory."""
    candidates = [
        PROJECT_ROOT / "seeds" / "profile.json",
        Path.cwd() / "seeds" / "profile.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "seeds/profile.json was not found. Run commands from the project root."
    )


class Settings(BaseSettings):
    """Runtime configuration. Secrets come from the environment, never from code."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""
    timezone: str = "Africa/Addis_Ababa"
    log_level: str = "INFO"
    embedding_model: str = Field(default=EMBEDDING_MODEL)
    embedding_dimensions: int = Field(default=EMBEDDING_DIMENSIONS)

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL SQLAlchemy URL")
        return value

    @field_validator("log_level")
    @classmethod
    def log_level_must_be_known(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("embedding_dimensions")
    @classmethod
    def embedding_dimensions_must_match_schema(cls, value: int) -> int:
        if value != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"EMBEDDING_DIMENSIONS must stay {EMBEDDING_DIMENSIONS} "
                "unless the vector columns are migrated."
            )
        return value

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        parse_user_ids(self.telegram_allowed_user_ids)
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown TIMEZONE: {self.timezone}") from exc
        return self

    @property
    def allowed_user_ids(self) -> frozenset[int]:
        return parse_user_ids(self.telegram_allowed_user_ids)


@lru_cache
def get_settings() -> Settings:
    return Settings()
