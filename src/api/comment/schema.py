from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    parent_id: int | None = Field(default=None, alias="parentId", ge=1)
    content: str = Field(min_length=1)
    password: str = Field(min_length=4, max_length=100)
    author: UUID | None = None


class CommentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1)
    password: str = Field(min_length=1, max_length=100)


class CommentDelete(BaseModel):
    password: str = Field(min_length=1, max_length=100)


class CommentResponse(BaseModel):
    comment_id: int = Field(serialization_alias="commentId")
    post_id: int = Field(serialization_alias="postId")
    parent_id: int | None = Field(serialization_alias="parentId")
    author: str
    content: str
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")
    children: list["CommentResponse"] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    message: str
