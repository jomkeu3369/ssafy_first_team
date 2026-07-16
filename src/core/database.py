from collections.abc import AsyncGenerator

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings
from src.core.ids import MAX_PUBLIC_ID


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


def _columns(sync_connection, table: str) -> set[str] | None:
    inspector = inspect(sync_connection)
    if table not in inspector.get_table_names():
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def _table_names(sync_connection) -> set[str]:
    return set(inspect(sync_connection).get_table_names())


async def _renumber_primary_key(connection, existing_tables: set[str], table: str, column: str, references: tuple[tuple[str, str], ...], start: int, preserved: set[int]) -> bool:
    if table not in existing_tables:
        return False

    preparer = connection.dialect.identifier_preparer
    table_name = preparer.quote(table)
    column_name = preparer.quote(column)
    result = await connection.execute(text(f"SELECT {column_name} FROM {table_name} ORDER BY {column_name}"))
    current_ids = [int(row[0]) for row in result if int(row[0]) not in preserved]
    if not any(current_id > MAX_PUBLIC_ID for current_id in current_ids):
        return False
    expected_ids = list(range(start, start + len(current_ids)))
    temporary_start = min([0, *current_ids]) - len(current_ids) - 1
    mappings = [(old_id, temporary_start + index, expected_ids[index]) for index, old_id in enumerate(current_ids)]
    active_references = [(preparer.quote(reference_table), preparer.quote(reference_column)) for reference_table, reference_column in references if reference_table in existing_tables]

    for old_id, temporary_id, _new_id in mappings:
        await connection.execute(text(f"UPDATE {table_name} SET {column_name} = :temporary_id WHERE {column_name} = :old_id"), {"temporary_id": temporary_id, "old_id": old_id})
        for reference_table, reference_column in active_references:
            await connection.execute(text(f"UPDATE {reference_table} SET {reference_column} = :temporary_id WHERE {reference_column} = :old_id"), {"temporary_id": temporary_id, "old_id": old_id})

    for _old_id, temporary_id, new_id in mappings:
        await connection.execute(text(f"UPDATE {table_name} SET {column_name} = :new_id WHERE {column_name} = :temporary_id"), {"new_id": new_id, "temporary_id": temporary_id})
        for reference_table, reference_column in active_references:
            await connection.execute(text(f"UPDATE {reference_table} SET {reference_column} = :new_id WHERE {reference_column} = :temporary_id"), {"new_id": new_id, "temporary_id": temporary_id})
    return True


async def _normalize_sqlite_ids(connection) -> bool:
    existing_tables = await connection.run_sync(_table_names)
    changed = False
    changed |= await _renumber_primary_key(connection, existing_tables, "Board", "boardId", (("post", "boardId"),), 1, {0})
    changed |= await _renumber_primary_key(connection, existing_tables, "post", "postId", (("comment", "postId"), ("media", "postId"), ("Post_Tags", "postId"), ("Post_Likes", "postId")), 1, set())
    changed |= await _renumber_primary_key(connection, existing_tables, "comment", "commentId", (("comment", "parentId"),), 1, set())
    changed |= await _renumber_primary_key(connection, existing_tables, "media", "mediaId", (), 1, set())
    changed |= await _renumber_primary_key(connection, existing_tables, "Tag", "tagId", (("Post_Tags", "tagId"),), 10, set(range(1, 10)))
    return changed


async def _apply_compatibility_updates(connection, normalize_ids: bool) -> bool:
    changed = False
    compatibility_columns = {"Board": {"nameKr": "VARCHAR(100) NULL", "nameEn": "VARCHAR(200) NULL", "categoryKr": "VARCHAR(100) NULL", "categoryEn": "VARCHAR(100) NULL", "descriptionKr": "VARCHAR(1000) NULL", "descriptionEn": "VARCHAR(2000) NULL", "image": "VARCHAR(2000) NULL", "contentId": "VARCHAR(100) NULL", "address": "VARCHAR(500) NULL", "addressEn": "VARCHAR(1000) NULL", "eventStartDate": "VARCHAR(8) NULL", "eventEndDate": "VARCHAR(8) NULL", "eventPlace": "VARCHAR(500) NULL", "eventPlaceEn": "VARCHAR(1000) NULL"}, "post": {"titleKr": "VARCHAR(500) NULL", "titleEn": "VARCHAR(500) NULL", "contentKr": "TEXT NULL", "contentEn": "TEXT NULL", "createdAt": "DATETIME NULL", "updatedAt": "DATETIME NULL"}, "comment": {"contentKr": "TEXT NULL", "contentEn": "TEXT NULL"}}
    for table, missing_columns in compatibility_columns.items():
        columns = await connection.run_sync(_columns, table)
        if columns is None:
            continue
        preparer = connection.dialect.identifier_preparer
        table_name = preparer.quote(table)
        for column, definition in missing_columns.items():
            if column in columns:
                continue
            column_name = preparer.quote(column)
            await connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))
            changed = True
    if normalize_ids:
        changed |= await _normalize_sqlite_ids(connection)
    return changed


async def ensure_database_compatibility(target_engine: AsyncEngine | None = None) -> bool:
    selected_engine = target_engine or engine
    if selected_engine.url.get_backend_name() != "sqlite":
        async with selected_engine.begin() as connection:
            return await _apply_compatibility_updates(connection, False)

    async with selected_engine.connect() as connection:
        await connection.execute(text("PRAGMA foreign_keys=OFF"))
        await connection.commit()
        try:
            async with connection.begin():
                changed = await _apply_compatibility_updates(connection, True)
                violations = (await connection.execute(text("PRAGMA foreign_key_check"))).all()
                if violations:
                    raise RuntimeError(f"Foreign key violations after ID normalization: {violations}")
        finally:
            if connection.in_transaction():
                await connection.rollback()
            await connection.execute(text("PRAGMA foreign_keys=ON"))
            await connection.commit()
        return changed


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
