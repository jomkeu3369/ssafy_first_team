from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.post import Post


class Board(Base):
    __tablename__ = "Board"
    __table_args__ = (
        UniqueConstraint("name", "category", name="uq_board_name_category"),
    )

    board_id: Mapped[int] = mapped_column("boardId", BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    posts: Mapped[list[Post]] = relationship(back_populates="board")
