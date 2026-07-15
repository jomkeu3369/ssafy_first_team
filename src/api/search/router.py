from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.search import crud
from src.api.search.schema import SearchResponse
from src.core.database import get_db_session


router = APIRouter(prefix="/search")


@router.get("", response_model=SearchResponse, response_model_by_alias=True)
async def search_all(q: Annotated[str, Query(min_length=1, max_length=200)], db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> SearchResponse:
    return await crud.search_all(db, q, page, size)
