from typing import Literal

from pydantic import BaseModel, Field


class SearchItem(BaseModel):
    result_type: Literal["BOARD", "POST"] = Field(serialization_alias="resultType")
    result_id: int = Field(serialization_alias="resultId")
    board_id: int = Field(serialization_alias="boardId")
    title: str
    description: str | None
    image: str
    category: str | None


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    page: int
    size: int
