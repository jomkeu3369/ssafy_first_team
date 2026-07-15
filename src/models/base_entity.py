from sqlalchemy import Column, String, Table

from src.models.base import Base


# The supplied BaseEntity has no primary key, so SQLAlchemy cannot map it as an
# ORM class. Keep it in the metadata as a Core table matching the given schema.
base_entity = Table(
    "BaseEntity",
    Base.metadata,
    Column("createdAt", String(255), nullable=True),
    Column("updatedAt", String(255), nullable=True),
)
