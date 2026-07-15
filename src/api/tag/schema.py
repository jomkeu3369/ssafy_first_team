from pydantic import BaseModel, Field


class TagResponse(BaseModel):
    tag_id: int = Field(serialization_alias="tagId")
    name: str
    category: str
