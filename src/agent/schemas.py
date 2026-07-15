from typing import Literal

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    language: Literal["ko", "en"] = "ko"
    history: list[HistoryMessage] = Field(default_factory=list, max_length=10)


class Reference(BaseModel):
    type: str
    id: str | None = None
    title: str | None = None
    address: str | None = None
    image_url: str | None = Field(default=None, serialization_alias="imageUrl")
    url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    language: Literal["ko", "en"]
    references: list[Reference] = Field(default_factory=list)
