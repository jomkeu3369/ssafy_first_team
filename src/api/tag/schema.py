from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=50)


class TagResponse(BaseModel):
    tag_id: int = Field(serialization_alias="tagId")
    name: str
    name_en: str = Field(serialization_alias="nameEn")
    category: str


class TagPageResponse(BaseModel):
    items: list[TagResponse]
    total: int
    page: int
    size: int


class ErrorResponse(BaseModel):
    message: str
