from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.like import crud
from src.api.like.schema import ErrorResponse, LikeResponse
from src.core.database import get_db_session


router = APIRouter()


def _error(message: str) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": message})


@router.post("/posts/{post_id}/likes", response_model=LikeResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def add_like(post_id: Annotated[int, Path(ge=0)], client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)]) -> LikeResponse | JSONResponse:
    try:
        return await crud.add_like(db, post_id, str(client_id))
    except crud.PostNotFoundError:
        return _error("게시글을 찾을 수 없습니다.")


@router.delete("/posts/{post_id}/likes", response_model=LikeResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def remove_like(post_id: Annotated[int, Path(ge=0)], client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)]) -> LikeResponse | JSONResponse:
    try:
        return await crud.remove_like(db, post_id, str(client_id))
    except crud.PostNotFoundError:
        return _error("게시글을 찾을 수 없습니다.")


@router.get("/posts/{post_id}/likes/me", response_model=LikeResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_my_like(post_id: Annotated[int, Path(ge=0)], client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)]) -> LikeResponse | JSONResponse:
    try:
        return await crud.get_my_like(db, post_id, str(client_id))
    except crud.PostNotFoundError:
        return _error("게시글을 찾을 수 없습니다.")
