from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.localization import ATTRACTION_CATEGORY_EN
from src.api.tourism import service
from src.api.tourism.schema import AttractionPageResponse, AttractionResponse, FestivalPageResponse, FestivalResponse
from src.models.board import Board


ATTRACTION_CATEGORY = "관광지"
FESTIVAL_CATEGORY = "축제공연행사"


def _content_id(board: Board) -> str:
    return board.source_content_id or str(board.board_id)


def _to_attraction(board: Board) -> AttractionResponse:
    address = board.address or ""
    category = service._attraction_category({"title": board.name, "addr1": address})
    summary = (board.description or f"부산의 {board.name}입니다.")[:200]
    summary_en = f"{board.name} is a Busan attraction" + (f" located at {address}." if address else ".")
    return AttractionResponse(board_id=board.board_id, content_id=_content_id(board), name=board.name, name_en=board.name, category=category, category_en=ATTRACTION_CATEGORY_EN[category.value], summary=summary, summary_en=summary_en, description=board.description or summary, description_en=summary_en, image=board.image or "", address=address, address_en=address)


def _to_festival(board: Board, today: date) -> FestivalResponse:
    start_date = service._parse_date(board.event_start_date)
    end_date = service._parse_date(board.event_end_date)
    period = " ~ ".join(value.isoformat() for value in (start_date, end_date) if value is not None)
    place = board.event_place or board.address or ""
    summary = (board.description or f"부산에서 열리는 {board.name}입니다.")[:200]
    summary_en = f"{board.name} is a festival held" + (f" at {place} in Busan." if place else " in Busan.")
    return FestivalResponse(board_id=board.board_id, content_id=_content_id(board), name=board.name, name_en=board.name, status=service._festival_status(start_date, end_date, today), place=place, place_en=place, period=period, period_en=period, start_date=start_date, end_date=end_date, image=board.image or "", summary=summary, summary_en=summary_en)


def _content_filter(content_id: str):
    conditions = [Board.source_content_id == content_id]
    if content_id.isdigit():
        conditions.append(Board.board_id == int(content_id))
    return or_(*conditions)


async def get_attractions(db: AsyncSession, page: int, size: int) -> AttractionPageResponse:
    category_filter = Board.category == ATTRACTION_CATEGORY
    total = await db.scalar(select(func.count(Board.board_id)).where(category_filter)) or 0
    statement = select(Board).where(category_filter).order_by(Board.name, Board.board_id).offset((page - 1) * size).limit(size)
    boards = (await db.scalars(statement)).all()
    return AttractionPageResponse(items=[_to_attraction(board) for board in boards], total=total, page=page, size=size)


async def get_attraction(db: AsyncSession, content_id: str) -> AttractionResponse | None:
    statement = select(Board).where(Board.category == ATTRACTION_CATEGORY, _content_filter(content_id))
    board = (await db.scalars(statement)).one_or_none()
    return _to_attraction(board) if board is not None else None


async def get_festivals(db: AsyncSession, page: int, size: int, today: date | None = None) -> FestivalPageResponse:
    category_filter = Board.category == FESTIVAL_CATEGORY
    total = await db.scalar(select(func.count(Board.board_id)).where(category_filter)) or 0
    statement = select(Board).where(category_filter).order_by(Board.event_start_date.desc(), Board.name, Board.board_id).offset((page - 1) * size).limit(size)
    boards = (await db.scalars(statement)).all()
    reference_date = today or date.today()
    return FestivalPageResponse(items=[_to_festival(board, reference_date) for board in boards], total=total, page=page, size=size)


async def get_festival(db: AsyncSession, content_id: str, today: date | None = None) -> FestivalResponse | None:
    statement = select(Board).where(Board.category == FESTIVAL_CATEGORY, _content_filter(content_id))
    board = (await db.scalars(statement)).one_or_none()
    return _to_festival(board, today or date.today()) if board is not None else None
