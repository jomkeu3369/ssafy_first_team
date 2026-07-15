from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.models.post_tag import post_tags

if TYPE_CHECKING:
    from src.models.post import Post


class Tag(Base):
    __tablename__ = "Tag"

    tag_id: Mapped[int] = mapped_column("tagId", BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    posts: Mapped[list[Post]] = relationship(
        secondary=post_tags,
        back_populates="tags",
    )
