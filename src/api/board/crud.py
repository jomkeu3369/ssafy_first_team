import asyncio

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.board.schema import BoardCreate, BoardPageResponse, BoardResponse
from src.core.ids import MAX_PUBLIC_ID
from src.models.board import Board
from src.models.media import Media
from src.models.post import Post


class BoardAlreadyExistsError(Exception):
    pass


_board_write_lock = asyncio.Lock()


async def _next_board_id(db: AsyncSession) -> int:
    return (await db.scalar(select(func.max(Board.board_id)).where(Board.board_id > 0, Board.board_id <= MAX_PUBLIC_ID)) or 0) + 1


def _board_select():
    post_count = select(func.count(Post.post_id)).where(Post.board_id == Board.board_id).correlate(Board).scalar_subquery()
    latest_title = select(Post.title).where(Post.board_id == Board.board_id).order_by(Post.post_id.desc()).limit(1).correlate(Board).scalar_subquery()
    latest_image = select(Media.image_url).join(Post, Media.post_id == Post.post_id).where(Post.board_id == Board.board_id).order_by(Post.post_id.desc(), Media.sequence, Media.media_id).limit(1).correlate(Board).scalar_subquery()
    return select(Board, post_count.label("recent_post_count"), latest_title.label("recent_excerpt"), latest_image.label("latest_image"))


def _to_response(row) -> BoardResponse:
    board = row[0]
    return BoardResponse(board_id=board.board_id, name=board.name, category=board.category, description=board.description, image=board.image or row.latest_image or "", recent_post_count=row.recent_post_count or 0, last_activity_at=None, recent_excerpt=row.recent_excerpt or "")


async def create_board(db: AsyncSession, board_create: BoardCreate) -> Board:
    async with _board_write_lock:
        duplicate_statement = select(Board.board_id).where(Board.name == board_create.name, Board.category == board_create.category)
        if await db.scalar(duplicate_statement) is not None:
            raise BoardAlreadyExistsError

        board = Board(board_id=await _next_board_id(db), **board_create.model_dump())
        db.add(board)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise

        await db.refresh(board)
        return board


async def get_boards(db: AsyncSession, page: int, size: int) -> BoardPageResponse:
    total = await db.scalar(select(func.count(Board.board_id))) or 0
    statement = _board_select().order_by(Board.category, Board.name, Board.board_id).offset((page - 1) * size).limit(size)
    rows = (await db.execute(statement)).all()
    return BoardPageResponse(items=[_to_response(row) for row in rows], total=total, page=page, size=size)


async def get_board(db: AsyncSession, board_id: int) -> BoardResponse | None:
    row = (await db.execute(_board_select().where(Board.board_id == board_id))).one_or_none()
    return _to_response(row) if row is not None else None
