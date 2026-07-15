import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.agent.router import router as chat_router
from src.api.board.router import router as board_router

from src.agent.service import AgentService
from src.core.config import get_settings
from src.core.database import dispose_engine, engine
from src.core.logging import get_logger


settings = get_settings()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Busan LocalHub server is starting")
    agent_service = AgentService(settings)
    app.state.agent_service = agent_service

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        try:
            await agent_service.start()
            logger.info("AI agent and MCP sessions are ready")
        except Exception as exc:
            logger.warning("AI agent is unavailable: %s", exc)
        yield
    finally:
        await agent_service.close()
        await dispose_engine()
        logger.info("Busan LocalHub server has stopped")


def configure_middleware(app: FastAPI) -> None:
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Accept", "Authorization", "Content-Type", "X-Client-Id"],
            expose_headers=["X-Request-ID"],
            max_age=3600,
        )

    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        if request.url.path in {"/health", "/version", "/favicon.ico"}:
            return await call_next(request)

        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        logger.info("START: %s %s [%s]", request.method, request.url.path, request_id)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "FAIL: %s %s [%s]", request.method, request.url.path, request_id
            )
            raise

        process_time_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "END: %s %s %s (%.2fms) [%s]",
            response.status_code,
            request.method,
            request.url.path,
            process_time_ms,
            request_id,
        )
        response.headers["X-Request-ID"] = request_id
        return response


def register_routes(app: FastAPI) -> None:
    @app.get("/version", tags=["system"])
    async def get_version() -> dict[str, str]:
        return {"version": settings.version}

    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed",
            ) from exc
        return {"status": "healthy", "database": "connected"}

    app.include_router(chat_router, prefix="/api/v1", tags=["AI"])
    app.include_router(board_router, prefix="/api/v1", tags=["Boards"])


def create_app() -> FastAPI:
    app = FastAPI(
        title="Busan LocalHub Server",
        version=settings.version,
        description="Busan LocalHub Server API",
        lifespan=lifespan,
        openapi_url="/openapi.json" if settings.enable_openapi else None,
        docs_url=(
            "/docs" if settings.enable_openapi and settings.enable_swagger_ui else None
        ),
        redoc_url=(
            "/redoc" if settings.enable_openapi and settings.enable_redoc else None
        ),
    )
    configure_middleware(app)
    register_routes(app)
    return app


app = create_app()
