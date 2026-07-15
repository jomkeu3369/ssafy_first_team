from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.post import Post


class Board(Base):
    __tablename__ = "Board"

    board_id: Mapped[int] = mapped_column("boardId", BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    posts: Mapped[list[Post]] = relationship(back_populates="board")
