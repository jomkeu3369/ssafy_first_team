from pydantic import BaseModel, Field


class LikeResponse(BaseModel):
    liked: bool
    like_count: int = Field(serialization_alias="likeCount")


class ErrorResponse(BaseModel):
    message: str
