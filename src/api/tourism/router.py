import asyncio
from typing import Annotated

from fastapi import APIRouter, Path, status
from fastapi.responses import JSONResponse

from src.api.tourism import service
from src.api.tourism.schema import AttractionResponse, ErrorResponse, FestivalResponse
from src.core.config import get_settings


router = APIRouter(prefix="/tourism")
settings = get_settings()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@router.get("/attractions", response_model=list[AttractionResponse], response_model_by_alias=True, responses={503: {"model": ErrorResponse}})
async def get_attractions() -> list[AttractionResponse] | JSONResponse:
    try:
        return await asyncio.to_thread(service.get_attractions, settings.tourism_data_dir)
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "관광 데이터 원본을 찾을 수 없습니다.")


@router.get("/attractions/{content_id}", response_model=AttractionResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def get_attraction(content_id: Annotated[str, Path(min_length=1, max_length=100)]) -> AttractionResponse | JSONResponse:
    try:
        return await asyncio.to_thread(service.get_attraction, settings.tourism_data_dir, content_id)
    except service.TourismContentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "관광지를 찾을 수 없습니다.")
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "관광 데이터 원본을 찾을 수 없습니다.")


@router.get("/festivals", response_model=list[FestivalResponse], response_model_by_alias=True, responses={503: {"model": ErrorResponse}})
async def get_festivals() -> list[FestivalResponse] | JSONResponse:
    try:
        return await asyncio.to_thread(service.get_festivals, settings.tourism_data_dir)
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "축제 데이터 원본을 찾을 수 없습니다.")


@router.get("/festivals/{content_id}", response_model=FestivalResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def get_festival(content_id: Annotated[str, Path(min_length=1, max_length=100)]) -> FestivalResponse | JSONResponse:
    try:
        return await asyncio.to_thread(service.get_festival, settings.tourism_data_dir, content_id)
    except service.TourismContentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "축제를 찾을 수 없습니다.")
    except service.TourismSourceUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "축제 데이터 원본을 찾을 수 없습니다.")
