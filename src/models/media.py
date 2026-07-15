from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.post import Post


class Media(Base):
    __tablename__ = "media"

    media_id: Mapped[int] = mapped_column("mediaId", BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        "postId",
        BigInteger,
        ForeignKey("post.postId"),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column("imageUrl", String, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    post: Mapped[Post] = relationship(back_populates="media")
