"""add comment translation fields

Revision ID: a42d91e7c305
Revises: 7c1b0a4d9e21
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a42d91e7c305"
down_revision: str | Sequence[str] | None = "7c1b0a4d9e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("comment")}


def upgrade() -> None:
    columns = _column_names()
    if "contentKr" not in columns:
        op.add_column("comment", sa.Column("contentKr", sa.Text(), nullable=True))
    if "contentEn" not in columns:
        op.add_column("comment", sa.Column("contentEn", sa.Text(), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text('UPDATE comment SET "contentKr" = content WHERE "contentKr" IS NULL'))
    if connection.dialect.name == "sqlite":
        connection.execute(sa.text('UPDATE comment SET "contentEn" = NULL WHERE "contentEn" GLOB :pattern'), {"pattern": "*[가-힣]*"})
    elif connection.dialect.name == "postgresql":
        connection.execute(sa.text('UPDATE comment SET "contentEn" = NULL WHERE "contentEn" ~ :pattern'), {"pattern": "[가-힣]"})


def downgrade() -> None:
    columns = _column_names()
    if "contentEn" in columns:
        op.drop_column("comment", "contentEn")
    if "contentKr" in columns:
        op.drop_column("comment", "contentKr")
