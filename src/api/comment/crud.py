import asyncio
import secrets

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.comment.schema import CommentCreate, CommentPageResponse, CommentResponse
from src.api.comment.translation import CommentTranslator
from src.api.post.passwords import hash_password, verify_password
from src.core.ids import MAX_PUBLIC_ID
from src.models.comment import Comment
from src.models.post import Post


DELETED_COMMENT_CONTENT = "삭제된 댓글입니다"
DELETED_COMMENT_CONTENT_EN = "This comment has been deleted."


class PostNotFoundError(Exception):
    pass


class CommentNotFoundError(Exception):
    pass


class ParentCommentNotFoundError(Exception):
    pass


class CommentDepthError(Exception):
    pass


class PasswordMismatchError(Exception):
    pass


_comment_write_lock = asyncio.Lock()


async def _next_comment_id(db: AsyncSession) -> int:
    return (await db.scalar(select(func.max(Comment.comment_id)).where(Comment.comment_id > 0, Comment.comment_id <= MAX_PUBLIC_ID)) or 0) + 1


def _to_response(comment: Comment) -> CommentResponse:
    return CommentResponse(comment_id=comment.comment_id, post_id=comment.post_id, parent_id=comment.parent_id, author=comment.author, content=comment.content_kr or comment.content, content_kr=comment.content_kr or comment.content, content_en=comment.content_en or "", created_at=None, updated_at=None, children=[])


async def get_comments(db: AsyncSession, post_id: int, page: int, size: int) -> CommentPageResponse:
    if await db.get(Post, post_id) is None:
        raise PostNotFoundError

    root_filter = (Comment.post_id == post_id, Comment.parent_id.is_(None))
    total = await db.scalar(select(func.count(Comment.comment_id)).where(*root_filter)) or 0
    root_statement = select(Comment).where(*root_filter).order_by(Comment.comment_id).offset((page - 1) * size).limit(size)
    roots = list((await db.scalars(root_statement)).all())
    root_ids = [comment.comment_id for comment in roots]
    child_statement = select(Comment).where(Comment.parent_id.in_(root_ids)).order_by(Comment.comment_id) if root_ids else None
    children = list((await db.scalars(child_statement)).all()) if child_statement is not None else []
    comments = [*roots, *children]
    nodes = {comment.comment_id: _to_response(comment) for comment in comments}
    for child in children:
        nodes[child.parent_id].children.append(nodes[child.comment_id])
    return CommentPageResponse(items=[nodes[comment.comment_id] for comment in roots], total=total, page=page, size=size)


async def create_comment(db: AsyncSession, post_id: int, payload: CommentCreate, author: str, translator: CommentTranslator) -> CommentResponse:
    if await db.get(Post, post_id) is None:
        raise PostNotFoundError

    if payload.parent_id is not None:
        parent = await db.get(Comment, payload.parent_id)
        if parent is None or parent.post_id != post_id:
            raise ParentCommentNotFoundError
        if parent.parent_id is not None:
            raise CommentDepthError

    async with _comment_write_lock:
        translated = await translator.translate(payload.content)
        comment = Comment(comment_id=await _next_comment_id(db), post_id=post_id, parent_id=payload.parent_id, author=author, content=payload.content, content_kr=translated.content_kr, content_en=translated.content_en, password=hash_password(payload.password))
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
    return _to_response(comment)


async def update_comment(db: AsyncSession, comment_id: int, content: str, password: str, translator: CommentTranslator) -> CommentResponse:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise CommentNotFoundError
    if not verify_password(password, comment.password):
        raise PasswordMismatchError

    translated = await translator.translate(content)
    comment.content = content
    comment.content_kr = translated.content_kr
    comment.content_en = translated.content_en
    await db.commit()
    await db.refresh(comment)
    return _to_response(comment)


async def delete_comment(db: AsyncSession, comment_id: int, password: str) -> None:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise CommentNotFoundError
    if not verify_password(password, comment.password):
        raise PasswordMismatchError

    child_exists = await db.scalar(select(Comment.comment_id).where(Comment.parent_id == comment_id).limit(1))
    if child_exists is not None:
        comment.content = DELETED_COMMENT_CONTENT
        comment.content_kr = DELETED_COMMENT_CONTENT
        comment.content_en = DELETED_COMMENT_CONTENT_EN
        comment.password = hash_password(secrets.token_urlsafe(32))
    else:
        await db.execute(delete(Comment).where(Comment.comment_id == comment_id))
    await db.commit()
