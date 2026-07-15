from pydantic import BaseModel, Field


class ImportResponse(BaseModel):
    source_count: int = Field(serialization_alias="sourceCount")
    inserted_count: int = Field(serialization_alias="insertedCount")
    updated_count: int = Field(serialization_alias="updatedCount")
    unchanged_count: int = Field(serialization_alias="unchangedCount")
    skipped_count: int = Field(serialization_alias="skippedCount")
    categories: dict[str, int]


class ErrorResponse(BaseModel):
    message: str
