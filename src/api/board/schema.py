from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoardCategory(StrEnum):
    FREE = "FREE"
    HAEUNDAE = "HAEUNDAE"
    GWANGALLI = "GWANGALLI"
    SEOMYEON = "SEOMYEON"
    NAMPODONG = "NAMPODONG"
    YEONGDO = "YEONGDO"
    GIJANG = "GIJANG"


class BoardCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    name: str = Field(min_length=1, max_length=100)
    category: BoardCategory
    description: str | None = Field(default=None, max_length=1000)


class BoardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    board_id: int = Field(serialization_alias="boardId")
    name: str
    category: str
    description: str | None
    image: str = ""
    recent_post_count: int = Field(default=0, serialization_alias="recentPostCount")
    last_activity_at: datetime | None = Field(default=None, serialization_alias="lastActivityAt")
    recent_excerpt: str = Field(default="", serialization_alias="recentExcerpt")

    @field_validator("image", mode="before")
    @classmethod
    def default_image(cls, value: str | None) -> str:
        return value or ""


class ErrorResponse(BaseModel):
    message: str
