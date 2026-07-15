from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class AttractionCategory(StrEnum):
    BEACH = "BEACH"
    DOWNTOWN = "DOWNTOWN"
    HISTORIC = "HISTORIC"
    SCENIC = "SCENIC"
    SUBURB = "SUBURB"


class FestivalStatus(StrEnum):
    ONGOING = "ONGOING"
    UPCOMING = "UPCOMING"
    ENDED = "ENDED"


class AttractionResponse(BaseModel):
    board_id: int | None = Field(default=None, serialization_alias="boardId")
    content_id: str = Field(serialization_alias="contentId")
    name: str
    name_en: str = Field(serialization_alias="nameEn")
    category: AttractionCategory
    category_en: str = Field(serialization_alias="categoryEn")
    summary: str
    summary_en: str = Field(serialization_alias="summaryEn")
    description: str
    description_en: str = Field(serialization_alias="descriptionEn")
    image: str
    address: str
    address_en: str = Field(serialization_alias="addressEn")


class AttractionPageResponse(BaseModel):
    items: list[AttractionResponse]
    total: int
    page: int
    size: int


class FestivalResponse(BaseModel):
    board_id: int | None = Field(default=None, serialization_alias="boardId")
    content_id: str = Field(serialization_alias="contentId")
    name: str
    name_en: str = Field(serialization_alias="nameEn")
    status: FestivalStatus
    place: str
    place_en: str = Field(serialization_alias="placeEn")
    period: str
    period_en: str = Field(serialization_alias="periodEn")
    start_date: date | None = Field(default=None, serialization_alias="startDate")
    end_date: date | None = Field(default=None, serialization_alias="endDate")
    image: str
    summary: str
    summary_en: str = Field(serialization_alias="summaryEn")


class FestivalPageResponse(BaseModel):
    items: list[FestivalResponse]
    total: int
    page: int
    size: int


class ErrorResponse(BaseModel):
    message: str
