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
    content_id: str = Field(serialization_alias="contentId")
    name: str
    category: AttractionCategory
    summary: str
    description: str
    image: str
    address: str


class FestivalResponse(BaseModel):
    content_id: str = Field(serialization_alias="contentId")
    name: str
    status: FestivalStatus
    place: str
    period: str
    start_date: date | None = Field(default=None, serialization_alias="startDate")
    end_date: date | None = Field(default=None, serialization_alias="endDate")
    image: str
    summary: str


class ErrorResponse(BaseModel):
    message: str
