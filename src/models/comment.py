from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.post import Post


class Comment(Base):
    __tablename__ = "comment"

    comment_id: Mapped[int] = mapped_column("commentId", BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        "postId",
        BigInteger,
        ForeignKey("post.postId"),
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(
        "parentId",
        BigInteger,
        ForeignKey("comment.commentId"),
        nullable=True,
    )
    author: Mapped[str] = mapped_column(String, nullable=False, comment="UUID")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)

    post: Mapped["Post"] = relationship(back_populates="comments")
    parent: Mapped[Comment | None] = relationship(
        back_populates="children",
        remote_side=[comment_id],
    )
    children: Mapped[list[Comment]] = relationship(back_populates="parent")
