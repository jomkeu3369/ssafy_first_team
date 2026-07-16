"""add localized board and post columns

Revision ID: f466616b2c85
Revises: 39af0654d1ee
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f466616b2c85"
down_revision: str | Sequence[str] | None = "39af0654d1ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_missing_column(table: str, column: sa.Column) -> None:
    if column.name not in _column_names(table):
        op.add_column(table, column)


def _drop_existing_column(table: str, column: str) -> None:
    if column in _column_names(table):
        op.drop_column(table, column)


def upgrade() -> None:
    _add_missing_column("Board", sa.Column("nameEn", sa.String(length=200), nullable=True))
    _add_missing_column("Board", sa.Column("descriptionEn", sa.String(length=2000), nullable=True))
    _add_missing_column("Board", sa.Column("image", sa.String(length=2000), nullable=True))
    _add_missing_column("Board", sa.Column("contentId", sa.String(length=100), nullable=True))
    _add_missing_column("Board", sa.Column("address", sa.String(length=500), nullable=True))
    _add_missing_column("Board", sa.Column("addressEn", sa.String(length=1000), nullable=True))
    _add_missing_column("Board", sa.Column("eventStartDate", sa.String(length=8), nullable=True))
    _add_missing_column("Board", sa.Column("eventEndDate", sa.String(length=8), nullable=True))
    _add_missing_column("Board", sa.Column("eventPlace", sa.String(length=500), nullable=True))
    _add_missing_column("Board", sa.Column("eventPlaceEn", sa.String(length=1000), nullable=True))
    _add_missing_column("post", sa.Column("titleKr", sa.String(length=500), nullable=True))
    _add_missing_column("post", sa.Column("titleEn", sa.String(length=500), nullable=True))
    _add_missing_column("post", sa.Column("contentKr", sa.Text(), nullable=True))
    _add_missing_column("post", sa.Column("contentEn", sa.Text(), nullable=True))
    _add_missing_column("post", sa.Column("createdAt", sa.DateTime(timezone=True), nullable=True))
    _add_missing_column("post", sa.Column("updatedAt", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ("updatedAt", "createdAt", "contentEn", "contentKr", "titleEn", "titleKr"):
        _drop_existing_column("post", column)
    for column in ("eventPlaceEn", "eventPlace", "eventEndDate", "eventStartDate", "addressEn", "address", "contentId", "image", "descriptionEn", "nameEn"):
        _drop_existing_column("Board", column)
