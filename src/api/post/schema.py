from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


TAG_CATEGORIES = {1: "ATTRACTION", 2: "FESTIVAL", 3: "FOOD", 4: "STAY", 5: "TRANSPORT", 6: "SHOPPING", 7: "PHOTO", 8: "QUESTION", 9: "REVIEW"}


class PostSort(StrEnum):
    LATEST = "latest"
    COMMENTS = "comments"
    VIEWS = "views"
    LIKES = "likes"


class TagInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    tag_id: int = Field(alias="tagId", ge=1)
    name: str = Field(min_length=1, max_length=50)
    category: str = Field(default="CUSTOM", min_length=1, max_length=30)


class MediaInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    media_id: int = Field(alias="mediaId", ge=0)
    image_url: str = Field(alias="imageUrl", min_length=1, max_length=2000)


class PostWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    tags: list[TagInput] = Field(default_factory=list, max_length=5)
    media: list[MediaInput] = Field(default_factory=list, max_length=10)
    password: str = Field(min_length=4, max_length=100)
    author: UUID | None = None

    @field_validator("tags")
    @classmethod
    def validate_unique_tags(cls, tags: list[TagInput]) -> list[TagInput]:
        if len({tag.tag_id for tag in tags}) != len(tags):
            raise ValueError("Duplicate tagId values are not allowed")
        return tags

    @field_validator("media")
    @classmethod
    def validate_unique_media(cls, media: list[MediaInput]) -> list[MediaInput]:
        if len({item.media_id for item in media}) != len(media):
            raise ValueError("Duplicate mediaId values are not allowed")
        return media


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=100)


class PasswordVerifyResponse(BaseModel):
    verified: bool


class TagResponse(BaseModel):
    tag_id: int = Field(serialization_alias="tagId")
    name: str
    name_en: str = Field(serialization_alias="nameEn")
    category: str


class MediaResponse(BaseModel):
    media_id: int = Field(serialization_alias="mediaId")
    image_url: str = Field(serialization_alias="imageUrl")


class PostResponse(BaseModel):
    post_id: int = Field(serialization_alias="postId")
    board_id: int = Field(serialization_alias="boardId")
    title: str
    title_kr: str = Field(serialization_alias="titleKr")
    title_en: str = Field(serialization_alias="titleEn")
    author: str
    content: str
    content_kr: str = Field(serialization_alias="contentKr")
    content_en: str = Field(serialization_alias="contentEn")
    view_count: int = Field(serialization_alias="viewCount")
    like_count: int = Field(serialization_alias="likeCount")
    comment_count: int = Field(serialization_alias="commentCount")
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")
    tags: list[TagResponse]
    media: list[MediaResponse]


class PostPageResponse(BaseModel):
    items: list[PostResponse]
    total: int
    page: int
    size: int


class ErrorResponse(BaseModel):
    message: str


def tag_category(tag_id: int) -> str:
    return TAG_CATEGORIES.get(tag_id, "CUSTOM")
