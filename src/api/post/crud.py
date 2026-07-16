import asyncio
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.post.passwords import hash_password, verify_password
from src.api.post.schema import MediaResponse, PostPageResponse, PostResponse, PostSort, PostWrite, TagResponse, tag_category
from src.api.post.translation import PostTranslator
from src.api.localization import tag_name_en
from src.api.tag.crud import DEFAULT_TAGS
from src.core.ids import MAX_PUBLIC_ID
from src.models.board import Board
from src.models.comment import Comment
from src.models.media import Media
from src.models.post import Post
from src.models.post_like import PostLike
from src.models.post_tag import post_tags
from src.models.tag import Tag


class BoardNotFoundError(Exception):
    pass


class PostNotFoundError(Exception):
    pass


class PasswordMismatchError(Exception):
    pass


class TagValidationError(Exception):
    pass


class MediaConflictError(Exception):
    pass


_post_write_lock = asyncio.Lock()
_view_lock = asyncio.Lock()
_viewed_clients: set[tuple[int, str]] = set()
KST = timezone(timedelta(hours=9))


def _as_kst(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(KST)


async def _next_post_id(db: AsyncSession) -> int:
    return (await db.scalar(select(func.max(Post.post_id)).where(Post.post_id > 0, Post.post_id <= MAX_PUBLIC_ID)) or 0) + 1


def _comment_count():
    return select(func.count(Comment.comment_id)).where(Comment.post_id == Post.post_id).correlate(Post).scalar_subquery()


def _post_select():
    return select(Post, _comment_count().label("comment_count")).options(selectinload(Post.tags), selectinload(Post.media))


def _to_response(row) -> PostResponse:
    post = row[0]
    tags = [TagResponse(tag_id=tag.tag_id, name=tag.name, name_en=tag_name_en(tag.tag_id, tag.name), category=tag_category(tag.tag_id)) for tag in sorted(post.tags, key=lambda item: item.tag_id)]
    media = [MediaResponse(media_id=item.media_id, image_url=item.image_url) for item in post.media]
    return PostResponse(post_id=post.post_id, board_id=post.board_id, title=post.title, title_kr=post.title_kr or post.title, title_en=post.title_en or post.title, author=post.author, content=post.content, content_kr=post.content_kr or post.content, content_en=post.content_en or post.content, view_count=post.view_count, like_count=post.like_count, comment_count=row.comment_count or 0, created_at=_as_kst(post.created_at), updated_at=_as_kst(post.updated_at), tags=tags, media=media)


async def _resolve_tags(db: AsyncSession, payload: PostWrite) -> list[Tag]:
    resolved: list[Tag] = []
    for item in payload.tags:
        expected_category = tag_category(item.tag_id)
        tag = await db.get(Tag, item.tag_id)
        if item.tag_id <= 9:
            expected_name = DEFAULT_TAGS[item.tag_id][0]
            if item.name != expected_name or item.category != expected_category:
                raise TagValidationError
        elif item.category != "CUSTOM" or tag is None or tag.name != item.name:
            raise TagValidationError
        if tag is None:
            tag = Tag(tag_id=item.tag_id, name=item.name)
            db.add(tag)
        resolved.append(tag)
    return resolved


async def _replace_media(db: AsyncSession, post_id: int, payload: PostWrite) -> None:
    await db.execute(delete(Media).where(Media.post_id == post_id))
    await db.flush()
    for sequence, item in enumerate(payload.media):
        existing = await db.get(Media, item.media_id)
        if existing is not None:
            raise MediaConflictError
        db.add(Media(media_id=item.media_id, post_id=post_id, image_url=item.image_url, sequence=sequence))


async def get_post(db: AsyncSession, post_id: int) -> PostResponse | None:
    row = (await db.execute(_post_select().where(Post.post_id == post_id))).one_or_none()
    return _to_response(row) if row is not None else None


async def get_posts(db: AsyncSession, board_id: int, keyword: str | None, tag_id: int | None, sort: PostSort, page: int, size: int) -> PostPageResponse:
    if await db.get(Board, board_id) is None:
        raise BoardNotFoundError

    filters = [Post.board_id == board_id]
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(Post.title.ilike(pattern), Post.title_kr.ilike(pattern), Post.title_en.ilike(pattern), Post.content.ilike(pattern), Post.content_kr.ilike(pattern), Post.content_en.ilike(pattern), Post.tags.any(Tag.name.ilike(pattern))))
    if tag_id is not None:
        filters.append(Post.tags.any(Tag.tag_id == tag_id))

    total = await db.scalar(select(func.count(Post.post_id)).where(*filters)) or 0
    comment_count = _comment_count()
    order_by = {PostSort.LATEST: Post.post_id.desc(), PostSort.COMMENTS: comment_count.desc(), PostSort.VIEWS: Post.view_count.desc(), PostSort.LIKES: Post.like_count.desc()}[sort]
    statement = _post_select().where(*filters).order_by(order_by, Post.post_id.desc()).offset((page - 1) * size).limit(size)
    rows = (await db.execute(statement)).all()
    return PostPageResponse(items=[_to_response(row) for row in rows], total=total, page=page, size=size)


async def get_popular_posts(db: AsyncSession, page: int, size: int) -> PostPageResponse:
    total = await db.scalar(select(func.count(Post.post_id))) or 0
    comment_count = _comment_count()
    statement = _post_select().order_by(Post.like_count.desc(), comment_count.desc(), Post.view_count.desc(), Post.post_id.desc()).offset((page - 1) * size).limit(size)
    rows = (await db.execute(statement)).all()
    return PostPageResponse(items=[_to_response(row) for row in rows], total=total, page=page, size=size)


async def create_post(db: AsyncSession, board_id: int, payload: PostWrite, author: str, translator: PostTranslator) -> PostResponse:
    if await db.get(Board, board_id) is None:
        raise BoardNotFoundError
    translated = await translator.translate(payload.title, payload.content)

    async with _post_write_lock:
        tags = await _resolve_tags(db, payload)
        now = datetime.now(UTC)
        post = Post(post_id=await _next_post_id(db), board_id=board_id, title=payload.title, title_kr=translated.title_kr, title_en=translated.title_en, author=author, content=payload.content, content_kr=translated.content_kr, content_en=translated.content_en, password=hash_password(payload.password), view_count=0, like_count=0, created_at=now, updated_at=now)
        post.tags = tags
        db.add(post)

        try:
            await db.flush()
            await _replace_media(db, post.post_id, payload)
            await db.commit()
        except (IntegrityError, MediaConflictError):
            await db.rollback()
            raise

    result = await get_post(db, post.post_id)
    if result is None:
        raise PostNotFoundError
    return result


async def update_post(db: AsyncSession, post_id: int, payload: PostWrite, translator: PostTranslator) -> PostResponse:
    statement = select(Post).options(selectinload(Post.tags), selectinload(Post.media)).where(Post.post_id == post_id)
    post = (await db.scalars(statement)).one_or_none()
    if post is None:
        raise PostNotFoundError
    if not verify_password(payload.password, post.password):
        raise PasswordMismatchError

    translated = await translator.translate(payload.title, payload.content)
    post.title = payload.title
    post.title_kr = translated.title_kr
    post.title_en = translated.title_en
    post.content = payload.content
    post.content_kr = translated.content_kr
    post.content_en = translated.content_en
    post.updated_at = datetime.now(UTC)
    post.tags = await _resolve_tags(db, payload)
    try:
        await _replace_media(db, post_id, payload)
        await db.commit()
    except (IntegrityError, MediaConflictError):
        await db.rollback()
        raise

    result = await get_post(db, post_id)
    if result is None:
        raise PostNotFoundError
    return result


async def delete_post(db: AsyncSession, post_id: int, password: str) -> None:
    post = await db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError
    if not verify_password(password, post.password):
        raise PasswordMismatchError

    await db.execute(delete(post_tags).where(post_tags.c["postId"] == post_id))
    await db.execute(delete(PostLike).where(PostLike.post_id == post_id))
    await db.execute(delete(Media).where(Media.post_id == post_id))
    await db.execute(delete(Comment).where(Comment.post_id == post_id))
    await db.delete(post)
    await db.commit()


async def verify_post_password(db: AsyncSession, post_id: int, password: str) -> None:
    post = await db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError
    if not verify_password(password, post.password):
        raise PasswordMismatchError


async def get_post_with_view(db: AsyncSession, post_id: int, client_id: str) -> PostResponse:
    post = await db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError

    view_key = (post_id, client_id)
    async with _view_lock:
        if view_key not in _viewed_clients:
            _viewed_clients.add(view_key)
            post.view_count += 1
            await db.commit()

    result = await get_post(db, post_id)
    if result is None:
        raise PostNotFoundError
    return result
