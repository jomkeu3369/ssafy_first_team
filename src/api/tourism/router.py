from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tourism import crud
from src.api.tourism.schema import AttractionPageResponse, AttractionResponse, ErrorResponse, FestivalPageResponse, FestivalResponse
from src.core.database import get_db_session


router = APIRouter(prefix="/tourism")


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@router.get("/attractions", response_model=AttractionPageResponse, response_model_by_alias=True)
async def get_attractions(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> AttractionPageResponse:
    return await crud.get_attractions(db, page, size)


@router.get("/attractions/{content_id}", response_model=AttractionResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_attraction(content_id: Annotated[str, Path(min_length=1, max_length=100)], db: Annotated[AsyncSession, Depends(get_db_session)]) -> AttractionResponse | JSONResponse:
    result = await crud.get_attraction(db, content_id)
    return result if result is not None else _error(status.HTTP_404_NOT_FOUND, "관광지를 찾을 수 없습니다.")


@router.get("/festivals", response_model=FestivalPageResponse, response_model_by_alias=True)
async def get_festivals(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> FestivalPageResponse:
    return await crud.get_festivals(db, page, size)


@router.get("/festivals/{content_id}", response_model=FestivalResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_festival(content_id: Annotated[str, Path(min_length=1, max_length=100)], db: Annotated[AsyncSession, Depends(get_db_session)]) -> FestivalResponse | JSONResponse:
    result = await crud.get_festival(db, content_id)
    return result if result is not None else _error(status.HTTP_404_NOT_FOUND, "축제를 찾을 수 없습니다.")
