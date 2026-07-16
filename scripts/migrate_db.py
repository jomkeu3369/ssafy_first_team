import asyncio

from src.core.database import dispose_engine
from src.core.migrations import run_database_migrations


async def main() -> None:
    try:
        await run_database_migrations()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
