import asyncio
from pathlib import Path
import shutil

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core.config import DEFAULT_DATABASE_PATH, PROJECT_ROOT, get_settings
from src.core.database import engine
from src.models import Base


ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
LEGACY_BASELINE_REVISION = "39af0654d1ee"
_migration_lock = asyncio.Lock()


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url
    return config


def _stamp_legacy_database(database_url: str) -> None:
    command.stamp(_alembic_config(database_url), LEGACY_BASELINE_REVISION)


def _upgrade_database(database_url: str) -> None:
    command.upgrade(_alembic_config(database_url), "head")


def _seed_sqlite_database(database_url: str, seed_path: Path | None) -> None:
    url = make_url(database_url)
    if seed_path is None or url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return
    target = Path(url.database)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    source = seed_path if seed_path.is_absolute() else PROJECT_ROOT / seed_path
    if target.exists() or not source.is_file() or target.resolve() == source.resolve():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _table_names(sync_connection) -> set[str]:
    return set(inspect(sync_connection).get_table_names())


async def _migration_state(target_engine: AsyncEngine) -> tuple[bool, bool]:
    async with target_engine.connect() as connection:
        tables = await connection.run_sync(_table_names)
        has_application_tables = bool(tables & set(Base.metadata.tables))
        has_version = False
        if "alembic_version" in tables:
            has_version = await connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) > 0
        return has_application_tables, has_version


async def run_database_migrations(database_url: str | None = None, target_engine: AsyncEngine | None = None, seed_path: Path | None = DEFAULT_DATABASE_PATH) -> None:
    selected_url = database_url or get_settings().database_url
    selected_engine = target_engine or engine
    async with _migration_lock:
        await asyncio.to_thread(_seed_sqlite_database, selected_url, seed_path)
        has_application_tables, has_version = await _migration_state(selected_engine)
        if has_application_tables and not has_version:
            await asyncio.to_thread(_stamp_legacy_database, selected_url)
        await asyncio.to_thread(_upgrade_database, selected_url)
