from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "localhub.db"
DEFAULT_FAISS_INDEX_PATH = PROJECT_ROOT / "data" / "faiss"
DEFAULT_MEDIA_PATH = PROJECT_ROOT / "data" / "media"
DEFAULT_TOURISM_DATA_PATH = Path.home() / "Desktop" / "data2" / "부산"


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
    vector_mcp_url: str | None = None
    vector_mcp_api_key: str | None = None
    vector_mcp_timeout_seconds: float = 5.0
    vector_mcp_host: str = "127.0.0.1"
    vector_mcp_port: int = 8001
    vector_mcp_public_host: str | None = None
    vector_source_url: str | None = None
    vector_source_api_key: str | None = None
    vector_source_timeout_seconds: float = 30.0
    vector_source_cache_seconds: int = 300
    media_dir: Path = DEFAULT_MEDIA_PATH
    tourism_data_dir: Path = DEFAULT_TOURISM_DATA_PATH
    data_import_api_key: str | None = None
    agent_recursion_limit: int = 8

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "localhub-rag-agent"

    public_frontend_origin: str = "https://saffybuffy.netlify.app"
    frontend_origins: str = "http://localhost:5173"
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
        candidates = [self.public_frontend_origin, *self.frontend_origins.split(",")]
        normalized = [origin.strip().rstrip("/") for origin in candidates if origin.strip()]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_cors_credentials(self) -> Self:
        if self.cors_allow_credentials and "*" in self.cors_origins:
            msg = "CORS credentials cannot be enabled with a wildcard origin"
            raise ValueError(msg)
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
