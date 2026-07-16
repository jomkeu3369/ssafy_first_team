"""split board Korean and English fields

Revision ID: 7c1b0a4d9e21
Revises: f466616b2c85
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "7c1b0a4d9e21"
down_revision: str | Sequence[str] | None = "f466616b2c85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_missing_column(table: str, column: sa.Column) -> None:
    if column.name not in _column_names(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add_missing_column("Board", sa.Column("nameKr", sa.String(length=100), nullable=True))
    _add_missing_column("Board", sa.Column("categoryKr", sa.String(length=100), nullable=True))
    _add_missing_column("Board", sa.Column("categoryEn", sa.String(length=100), nullable=True))
    _add_missing_column("Board", sa.Column("descriptionKr", sa.String(length=1000), nullable=True))
    connection = op.get_bind()
    connection.execute(sa.text('UPDATE "Board" SET "nameKr" = name WHERE "nameKr" IS NULL'))
    connection.execute(sa.text('UPDATE "Board" SET "categoryKr" = category WHERE "categoryKr" IS NULL'))
    connection.execute(sa.text('UPDATE "Board" SET "descriptionKr" = description WHERE "descriptionKr" IS NULL'))
    connection.execute(sa.text('''UPDATE "Board" SET "categoryEn" = CASE category WHEN 'FREE' THEN 'Free Board' WHEN 'HAEUNDAE' THEN 'Haeundae' WHEN 'GWANGALLI' THEN 'Gwangalli' WHEN 'SEOMYEON' THEN 'Seomyeon' WHEN 'NAMPODONG' THEN 'Nampo-dong' WHEN 'YEONGDO' THEN 'Yeongdo' WHEN 'GIJANG' THEN 'Gijang' WHEN '관광지' THEN 'Attractions' WHEN '레포츠' THEN 'Leisure Sports' WHEN '문화시설' THEN 'Cultural Facilities' WHEN '쇼핑' THEN 'Shopping' WHEN '숙박' THEN 'Accommodations' WHEN '여행코스' THEN 'Travel Courses' WHEN '축제공연행사' THEN 'Festivals and Events' ELSE "categoryEn" END WHERE "categoryEn" IS NULL'''))
    english_columns = ("nameEn", "descriptionEn", "addressEn", "eventPlaceEn")
    if connection.dialect.name == "sqlite":
        for column in english_columns:
            connection.execute(sa.text(f'UPDATE "Board" SET "{column}" = NULL WHERE "{column}" GLOB :pattern'), {"pattern": "*[가-힣]*"})
    elif connection.dialect.name == "postgresql":
        for column in english_columns:
            connection.execute(sa.text(f'UPDATE "Board" SET "{column}" = NULL WHERE "{column}" ~ :pattern'), {"pattern": "[가-힣]"})


def downgrade() -> None:
    columns = _column_names("Board")
    for column in ("descriptionKr", "categoryEn", "categoryKr", "nameKr"):
        if column in columns:
            op.drop_column("Board", column)
