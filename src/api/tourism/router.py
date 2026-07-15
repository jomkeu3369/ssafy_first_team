import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tourism import service
from src.api.tourism.schema import AttractionPageResponse, AttractionResponse, ErrorResponse, FestivalPageResponse, FestivalResponse
from src.core.config import get_settings
from src.core.database import get_db_session
from src.models.board import Board


router = APIRouter(prefix="/tourism")
settings = get_settings()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


async def _attach_board_ids(db: AsyncSession, items: list[AttractionResponse] | list[FestivalResponse], category: str) -> None:
    names = {item.name for item in items}
    if not names:
        return
    statement = select(Board.board_id, Board.name).where(Board.category == category, Board.name.in_(names))
    board_ids = {name: board_id for board_id, name in (await db.execute(statement)).all()}
    for item in items:
        item.board_id = board_ids.get(item.name)


@router.get("/attractions", response_model=AttractionPageResponse, response_model_by_alias=True, responses={503: {"model": ErrorResponse}})
async def get_attractions(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> AttractionPageResponse | JSONResponse:
    try:
        result = await asyncio.to_thread(service.get_attraction_page, settings.tourism_data_dir, page, size)
        await _attach_board_ids(db, result.items, "관광지")
        return result
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "관광 데이터 원본을 찾을 수 없습니다.")


@router.get("/attractions/{content_id}", response_model=AttractionResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def get_attraction(content_id: Annotated[str, Path(min_length=1, max_length=100)], db: Annotated[AsyncSession, Depends(get_db_session)]) -> AttractionResponse | JSONResponse:
    try:
        result = await asyncio.to_thread(service.get_attraction, settings.tourism_data_dir, content_id)
        await _attach_board_ids(db, [result], "관광지")
        return result
    except service.TourismContentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "관광지를 찾을 수 없습니다.")
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "관광 데이터 원본을 찾을 수 없습니다.")


@router.get("/festivals", response_model=FestivalPageResponse, response_model_by_alias=True, responses={503: {"model": ErrorResponse}})
async def get_festivals(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> FestivalPageResponse | JSONResponse:
    try:
        result = await asyncio.to_thread(service.get_festival_page, settings.tourism_data_dir, page, size)
        await _attach_board_ids(db, result.items, "축제공연행사")
        return result
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "축제 데이터 원본을 찾을 수 없습니다.")


@router.get("/festivals/{content_id}", response_model=FestivalResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def get_festival(content_id: Annotated[str, Path(min_length=1, max_length=100)], db: Annotated[AsyncSession, Depends(get_db_session)]) -> FestivalResponse | JSONResponse:
    try:
        result = await asyncio.to_thread(service.get_festival, settings.tourism_data_dir, content_id)
        await _attach_board_ids(db, [result], "축제공연행사")
        return result
    except service.TourismContentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "축제를 찾을 수 없습니다.")
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "축제 데이터 원본을 찾을 수 없습니다.")
