from pydantic import BaseModel, Field


class MediaUploadResponse(BaseModel):
    media_id: int = Field(serialization_alias="mediaId")
    image_url: str = Field(serialization_alias="imageUrl")


class ErrorResponse(BaseModel):
    message: str
