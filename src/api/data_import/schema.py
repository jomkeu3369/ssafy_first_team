from pydantic import BaseModel, Field


class ImportResponse(BaseModel):
    source_count: int = Field(serialization_alias="sourceCount")
    inserted_count: int = Field(serialization_alias="insertedCount")
    updated_count: int = Field(serialization_alias="updatedCount")
    unchanged_count: int = Field(serialization_alias="unchangedCount")
    skipped_count: int = Field(serialization_alias="skippedCount")
    categories: dict[str, int]


class BoardTranslationResponse(BaseModel):
    requested_count: int = Field(serialization_alias="requestedCount")
    translated_count: int = Field(serialization_alias="translatedCount")
    remaining_count: int = Field(serialization_alias="remainingCount")


class CommentTranslationResponse(BaseModel):
    requested_count: int = Field(serialization_alias="requestedCount")
    translated_count: int = Field(serialization_alias="translatedCount")
    remaining_count: int = Field(serialization_alias="remainingCount")


class FaissIndexResponse(BaseModel):
    indexed_count: int = Field(serialization_alias="indexedCount")
    fingerprint: str
    embedding_model: str = Field(serialization_alias="embeddingModel")
    rebuilt: bool


class FaissIndexStatusResponse(BaseModel):
    ready: bool
    stale: bool
    document_count: int = Field(serialization_alias="documentCount")
    indexed_count: int = Field(serialization_alias="indexedCount")
    fingerprint: str
    embedding_model: str | None = Field(serialization_alias="embeddingModel")
    built_at: str | None = Field(serialization_alias="builtAt")


class ErrorResponse(BaseModel):
    message: str
