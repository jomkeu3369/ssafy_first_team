from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./localhub.db"
    database_echo: bool = False
    frontend_origins: str = "http://localhost:5173"
    cors_allow_credentials: bool = False
    enable_openapi: bool = True
    enable_swagger_ui: bool = True
    enable_redoc: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
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
