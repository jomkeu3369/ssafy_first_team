from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.core.database import engine


SEARCHABLE_TABLES: dict[str, dict[str, list[str]]] = {"Board": {"id": ["boardId"], "title": ["name", "nameKr", "nameEn"], "content": ["description", "descriptionKr", "descriptionEn", "eventPlace", "eventPlaceEn"], "address": ["address", "addressEn"], "image_url": ["image"], "region": [], "category": ["category", "categoryKr", "categoryEn"]}, "post": {"id": ["postId"], "title": ["title", "titleKr", "titleEn"], "content": ["content", "contentKr", "contentEn"], "address": [], "image_url": [], "region": [], "category": []}}
CONTENT_TYPE_ALIASES = {"board": "Board", "boards": "Board", "regional_contents": "Board", "post": "post", "posts": "post"}


def _first_existing(candidates: list[str], columns: set[str]) -> str | None:
    return next((name for name in candidates if name in columns), None)


def _select_expression(column: str | None, alias: str) -> str:
    return f'"{column}" AS "{alias}"' if column else f'NULL AS "{alias}"'


def _requested_tables(content_type: str | None) -> list[str]:
    if content_type is None:
        return list(SEARCHABLE_TABLES)
    table = CONTENT_TYPE_ALIASES.get(content_type.strip().lower())
    return [table] if table is not None else list(SEARCHABLE_TABLES)


async def search_sqlite_database(keyword: str, content_type: str | None = None, region: str | None = None, limit: int = 5) -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    items: list[dict[str, Any]] = []

    async with engine.connect() as connection:
        existing = await connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
        existing_tables = {row[0] for row in existing}

        for table in _requested_tables(content_type):
            if table not in existing_tables or len(items) >= limit:
                continue
            pragma = await connection.execute(text(f'PRAGMA table_info("{table}")'))
            columns = {row[1] for row in pragma}
            aliases = SEARCHABLE_TABLES[table]
            selected = {key: _first_existing(candidates, columns) for key, candidates in aliases.items()}
            search_columns = list(dict.fromkeys(column for key in ("title", "content", "address") for column in aliases[key] if column in columns))
            if not search_columns:
                continue

            select_parts = [_select_expression(selected[key], key) for key in ("id", "title", "content", "address", "image_url", "category")]
            where_parts = ["(" + " OR ".join(f"COALESCE(\"{column}\", '') LIKE :keyword" for column in search_columns) + ")"]
            parameters: dict[str, Any] = {"keyword": f"%{keyword.strip()}%", "limit": limit - len(items)}
            if region and selected["region"]:
                where_parts.append(f"COALESCE(\"{selected['region']}\", '') LIKE :region")
                parameters["region"] = f"%{region.strip()}%"

            statement = text(f'SELECT {", ".join(select_parts)} FROM "{table}" WHERE {" AND ".join(where_parts)} LIMIT :limit')
            result = await connection.execute(statement, parameters)
            for row in result.mappings():
                items.append({"sourceType": table, "sourceId": str(row["id"] if row["id"] is not None else ""), "title": row["title"], "content": row["content"], "address": row["address"], "imageUrl": row["image_url"], "category": row["category"]})

    return {"items": items}
