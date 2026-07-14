from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import dispose_engine, engine


settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))

    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(
    title="부산 소개 및 익명 게시판 플랫폼",
    description="부산 소개 및 익명 게시판 플랫폼 API 문서입니다.",
    version="0.1.0",
    lifespan=lifespan,
    openapi_url="/openapi.json" if settings.enable_openapi else None,
    docs_url=(
        "/docs"
        if settings.enable_openapi and settings.enable_swagger_ui
        else None
    ),
    redoc_url=(
        "/redoc" if settings.enable_openapi and settings.enable_redoc else None
    ),
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-Client-Id"],
    )


@app.get("/health", tags=["system"], summary="Check server health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
