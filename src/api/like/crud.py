import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.like.schema import LikeResponse
from src.models.post import Post
from src.models.post_like import PostLike


class PostNotFoundError(Exception):
    pass


_like_write_lock = asyncio.Lock()


async def get_my_like(db: AsyncSession, post_id: int, client_id: str) -> LikeResponse:
    post = await db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError
    liked = await db.get(PostLike, (post_id, client_id)) is not None
    return LikeResponse(liked=liked, like_count=post.like_count)


async def add_like(db: AsyncSession, post_id: int, client_id: str) -> LikeResponse:
    async with _like_write_lock:
        post = await db.get(Post, post_id)
        if post is None:
            raise PostNotFoundError
        if await db.get(PostLike, (post_id, client_id)) is None:
            db.add(PostLike(post_id=post_id, client_id=client_id))
            post.like_count += 1
            await db.commit()
        return LikeResponse(liked=True, like_count=post.like_count)


async def remove_like(db: AsyncSession, post_id: int, client_id: str) -> LikeResponse:
    async with _like_write_lock:
        post = await db.get(Post, post_id)
        if post is None:
            raise PostNotFoundError
        like = await db.get(PostLike, (post_id, client_id))
        if like is not None:
            await db.delete(like)
            post.like_count = max(0, post.like_count - 1)
            await db.commit()
        return LikeResponse(liked=False, like_count=post.like_count)
