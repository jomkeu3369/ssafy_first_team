from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.post_tag import post_tags

if TYPE_CHECKING:
    from src.models.board import Board
    from src.models.comment import Comment
    from src.models.media import Media
    from src.models.tag import Tag


class Post(Base):
    __tablename__ = "post"

    post_id: Mapped[int] = mapped_column("postId", BigInteger, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        "boardId",
        BigInteger,
        ForeignKey("Board.boardId"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    title_kr: Mapped[str | None] = mapped_column("titleKr", String(500), nullable=True)
    title_en: Mapped[str | None] = mapped_column("titleEn", String(500), nullable=True)
    author: Mapped[str] = mapped_column(String, nullable=False, comment="UUID")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_kr: Mapped[str | None] = mapped_column("contentKr", Text, nullable=True)
    content_en: Mapped[str | None] = mapped_column("contentEn", Text, nullable=True)
    password: Mapped[str] = mapped_column(String, nullable=False)
    view_count: Mapped[int] = mapped_column("viewCount", Integer, nullable=False)
    like_count: Mapped[int] = mapped_column("likeCount", Integer, nullable=False)

    board: Mapped[Board] = relationship(back_populates="posts")
    comments: Mapped[list[Comment]] = relationship(back_populates="post")
    media: Mapped[list[Media]] = relationship(
        back_populates="post",
        order_by="Media.sequence",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=post_tags,
        back_populates="posts"
    )
