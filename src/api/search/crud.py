from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.search.schema import SearchItem, SearchResponse
from src.models.board import Board
from src.models.media import Media
from src.models.post import Post
from src.models.tag import Tag


def _latest_post_image():
    return select(Media.image_url).where(Media.post_id == Post.post_id).order_by(Media.sequence, Media.media_id).limit(1).correlate(Post).scalar_subquery()


def _excerpt(value: str | None, max_length: int = 300) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text[:max_length] or None


async def search_all(db: AsyncSession, query: str, page: int, size: int) -> SearchResponse:
    pattern = f"%{query.strip()}%"
    board_search = select(literal("BOARD").label("result_type"), Board.board_id.label("result_id"), Board.board_id.label("board_id"), Board.name.label("title"), Board.description.label("description"), Board.image.label("image"), Board.category.label("category")).where(or_(Board.name.ilike(pattern), Board.description.ilike(pattern), Board.category.ilike(pattern)))
    post_search = select(literal("POST").label("result_type"), Post.post_id.label("result_id"), Post.board_id.label("board_id"), Post.title.label("title"), Post.content.label("description"), _latest_post_image().label("image"), literal(None).label("category")).where(or_(Post.title.ilike(pattern), Post.content.ilike(pattern), Post.tags.any(Tag.name.ilike(pattern))))
    combined = union_all(board_search, post_search).subquery()
    total = await db.scalar(select(func.count()).select_from(combined)) or 0
    statement = select(combined).order_by(combined.c.result_type, combined.c.title, combined.c.result_id).offset((page - 1) * size).limit(size)
    rows = (await db.execute(statement)).mappings().all()
    items = [SearchItem(result_type=row["result_type"], result_id=row["result_id"], board_id=row["board_id"], title=row["title"], description=_excerpt(row["description"]), image=row["image"] or "", category=row["category"]) for row in rows]
    return SearchResponse(items=items, total=total, page=page, size=size)
