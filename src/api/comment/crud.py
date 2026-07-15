import asyncio
import secrets

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.comment.schema import CommentCreate, CommentResponse
from src.api.post.passwords import hash_password, verify_password
from src.models.comment import Comment
from src.models.post import Post


DELETED_COMMENT_CONTENT = "삭제된 댓글입니다"


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


def _generate_comment_id() -> int:
    return secrets.randbelow(2**63 - 1) + 1


def _to_response(comment: Comment) -> CommentResponse:
    return CommentResponse(comment_id=comment.comment_id, post_id=comment.post_id, parent_id=comment.parent_id, author=comment.author, content=comment.content, created_at=None, updated_at=None, children=[])


async def get_comments(db: AsyncSession, post_id: int) -> list[CommentResponse]:
    if await db.get(Post, post_id) is None:
        raise PostNotFoundError

    statement = select(Comment).where(Comment.post_id == post_id).order_by(Comment.comment_id)
    comments = list((await db.scalars(statement)).all())
    nodes = {comment.comment_id: _to_response(comment) for comment in comments}
    roots: list[CommentResponse] = []
    for comment in comments:
        node = nodes[comment.comment_id]
        parent = nodes.get(comment.parent_id) if comment.parent_id is not None else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


async def create_comment(db: AsyncSession, post_id: int, payload: CommentCreate, author: str) -> CommentResponse:
    if await db.get(Post, post_id) is None:
        raise PostNotFoundError

    if payload.parent_id is not None:
        parent = await db.get(Comment, payload.parent_id)
        if parent is None or parent.post_id != post_id:
            raise ParentCommentNotFoundError
        if parent.parent_id is not None:
            raise CommentDepthError

    async with _comment_write_lock:
        comment_id = _generate_comment_id()
        while await db.get(Comment, comment_id) is not None:
            comment_id = _generate_comment_id()
        comment = Comment(comment_id=comment_id, post_id=post_id, parent_id=payload.parent_id, author=author, content=payload.content, password=hash_password(payload.password))
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
    return _to_response(comment)


async def update_comment(db: AsyncSession, comment_id: int, content: str, password: str) -> CommentResponse:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise CommentNotFoundError
    if not verify_password(password, comment.password):
        raise PasswordMismatchError

    comment.content = content
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
        comment.password = hash_password(secrets.token_urlsafe(32))
    else:
        await db.execute(delete(Comment).where(Comment.comment_id == comment_id))
    await db.commit()
