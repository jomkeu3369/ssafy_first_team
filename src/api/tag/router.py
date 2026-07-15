from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tag import crud
from src.api.tag.schema import TagResponse
from src.core.database import get_db_session


router = APIRouter(prefix="/tags")


@router.get("", response_model=list[TagResponse], response_model_by_alias=True)
async def get_tags(db: Annotated[AsyncSession, Depends(get_db_session)]) -> list[TagResponse]:
    return await crud.get_tags(db)
