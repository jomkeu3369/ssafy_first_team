from collections.abc import AsyncGenerator

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings


settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
)


if engine.url.get_backend_name() == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


def _board_columns(sync_connection) -> set[str] | None:
    inspector = inspect(sync_connection)
    if "Board" not in inspector.get_table_names():
        return None
    return {column["name"] for column in inspector.get_columns("Board")}


async def ensure_database_compatibility(target_engine: AsyncEngine | None = None) -> bool:
    selected_engine = target_engine or engine
    async with selected_engine.begin() as connection:
        columns = await connection.run_sync(_board_columns)
        if columns is None or "image" in columns:
            return False

        preparer = connection.dialect.identifier_preparer
        table_name = preparer.quote("Board")
        column_name = preparer.quote("image")
        await connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} VARCHAR(2000) NULL"))
        return True


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
