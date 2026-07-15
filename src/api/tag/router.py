from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tag import crud
from src.api.tag.schema import ErrorResponse, TagCreate, TagPageResponse, TagResponse
from src.core.database import get_db_session


router = APIRouter(prefix="/tags")


@router.get("", response_model=TagPageResponse, response_model_by_alias=True)
async def get_tags(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> TagPageResponse:
    return await crud.get_tags(db, page, size)


@router.post("", response_model=TagResponse, response_model_by_alias=True, status_code=status.HTTP_201_CREATED, responses={409: {"model": ErrorResponse}})
async def create_tag(payload: TagCreate, db: Annotated[AsyncSession, Depends(get_db_session)]) -> TagResponse | JSONResponse:
    try:
        return await crud.create_tag(db, payload)
    except crud.TagAlreadyExistsError:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"message": "같은 이름의 태그가 이미 존재합니다."})
    except IntegrityError:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"message": "태그를 생성하지 못했습니다."})
