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
    name_kr: Mapped[str | None] = mapped_column("nameKr", String(100), nullable=True)
    name_en: Mapped[str | None] = mapped_column("nameEn", String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    category_kr: Mapped[str | None] = mapped_column("categoryKr", String(100), nullable=True)
    category_en: Mapped[str | None] = mapped_column("categoryEn", String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description_kr: Mapped[str | None] = mapped_column("descriptionKr", String(1000), nullable=True)
    description_en: Mapped[str | None] = mapped_column("descriptionEn", String(2000), nullable=True)
    image: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_content_id: Mapped[str | None] = mapped_column("contentId", String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address_en: Mapped[str | None] = mapped_column("addressEn", String(1000), nullable=True)
    event_start_date: Mapped[str | None] = mapped_column("eventStartDate", String(8), nullable=True)
    event_end_date: Mapped[str | None] = mapped_column("eventEndDate", String(8), nullable=True)
    event_place: Mapped[str | None] = mapped_column("eventPlace", String(500), nullable=True)
    event_place_en: Mapped[str | None] = mapped_column("eventPlaceEn", String(1000), nullable=True)

    posts: Mapped[list[Post]] = relationship(back_populates="board")
