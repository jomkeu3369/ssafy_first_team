from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.api.localization import BOARD_CATEGORY_EN, board_description_en, board_name_en


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
    name_en: str = Field(default="", serialization_alias="nameEn")
    category: str
    category_en: str = Field(default="", serialization_alias="categoryEn")
    description: str | None
    description_en: str | None = Field(default=None, serialization_alias="descriptionEn")
    image: str = ""
    recent_post_count: int = Field(default=0, serialization_alias="recentPostCount")
    last_activity_at: datetime | None = Field(default=None, serialization_alias="lastActivityAt")
    recent_excerpt: str = Field(default="", serialization_alias="recentExcerpt")

    @field_validator("image", mode="before")
    @classmethod
    def default_image(cls, value: str | None) -> str:
        return value or ""

    @model_validator(mode="after")
    def populate_english_fields(self):
        self.name_en = self.name_en or board_name_en(self.name, self.category)
        self.category_en = self.category_en or BOARD_CATEGORY_EN.get(self.category, self.category)
        self.description_en = self.description_en or board_description_en(self.description)
        return self


class BoardPageResponse(BaseModel):
    items: list[BoardResponse]
    total: int
    page: int
    size: int


class ErrorResponse(BaseModel):
    message: str
