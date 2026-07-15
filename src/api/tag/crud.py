import asyncio

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tag.schema import TagCreate, TagPageResponse, TagResponse
from src.api.localization import tag_name_en
from src.core.ids import MAX_PUBLIC_ID
from src.models.tag import Tag


DEFAULT_TAGS = {1: ("관광지", "ATTRACTION"), 2: ("축제", "FESTIVAL"), 3: ("맛집", "FOOD"), 4: ("숙소", "STAY"), 5: ("교통", "TRANSPORT"), 6: ("쇼핑", "SHOPPING"), 7: ("사진", "PHOTO"), 8: ("질문", "QUESTION"), 9: ("후기", "REVIEW")}
_tag_write_lock = asyncio.Lock()


class TagAlreadyExistsError(Exception):
    pass


async def get_tags(db: AsyncSession, page: int, size: int) -> TagPageResponse:
    offset = (page - 1) * size
    default_responses = [TagResponse(tag_id=tag_id, name=name, name_en=tag_name_en(tag_id, name), category=category) for tag_id, (name, category) in DEFAULT_TAGS.items()]
    custom_filter = Tag.tag_id.not_in(DEFAULT_TAGS)
    custom_total = await db.scalar(select(func.count(Tag.tag_id)).where(custom_filter)) or 0
    items = default_responses[offset:min(offset + size, len(default_responses))] if offset < len(default_responses) else []
    custom_offset = max(offset - len(default_responses), 0)
    custom_size = size - len(items)
    if custom_size > 0 and custom_offset < custom_total:
        statement = select(Tag).where(custom_filter).order_by(Tag.tag_id).offset(custom_offset).limit(custom_size)
        custom_tags = (await db.scalars(statement)).all()
        items.extend(TagResponse(tag_id=tag.tag_id, name=tag.name, name_en=tag_name_en(tag.tag_id, tag.name), category="CUSTOM") for tag in custom_tags)
    return TagPageResponse(items=items, total=len(default_responses) + custom_total, page=page, size=size)


async def create_tag(db: AsyncSession, payload: TagCreate) -> TagResponse:
    async with _tag_write_lock:
        default_names = {name.casefold() for name, _category in DEFAULT_TAGS.values()}
        if payload.name.casefold() in default_names:
            raise TagAlreadyExistsError

        duplicate = await db.scalar(select(Tag.tag_id).where(func.lower(Tag.name) == payload.name.lower()))
        if duplicate is not None:
            raise TagAlreadyExistsError

        max_tag_id = await db.scalar(select(func.max(Tag.tag_id)).where(Tag.tag_id <= MAX_PUBLIC_ID)) or 9
        tag = Tag(tag_id=max(max_tag_id, 9) + 1, name=payload.name)
        db.add(tag)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise
        return TagResponse(tag_id=tag.tag_id, name=tag.name, name_en=tag_name_en(tag.tag_id, tag.name), category="CUSTOM")
