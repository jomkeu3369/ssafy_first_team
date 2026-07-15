from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "localhub.db"
DEFAULT_FAISS_INDEX_PATH = PROJECT_ROOT / "data" / "faiss"


class Settings(BaseSettings):
    environment: str = "development"
    version: str = "0.1.0"

    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    database_echo: bool = False

    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    tavily_api_key: str | None = None
    faiss_index_dir: Path = DEFAULT_FAISS_INDEX_PATH
    agent_recursion_limit: int = 8

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "localhub-rag-agent"

    frontend_origins: str = (
        "http://127.0.0.1:5500,http://localhost:5500,http://localhost:5173"
    )
    cors_allow_credentials: bool = False

    enable_openapi: bool = True
    enable_swagger_ui: bool = True
    enable_redoc: bool = False

    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.frontend_origins.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def validate_cors_credentials(self) -> Self:
        if self.cors_allow_credentials and "*" in self.cors_origins:
            msg = "CORS credentials cannot be enabled with a wildcard origin"
            raise ValueError(msg)
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
