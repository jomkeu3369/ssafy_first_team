import asyncio

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.tag.schema import TagCreate, TagResponse
from src.models.tag import Tag


DEFAULT_TAGS = {1: ("관광지", "ATTRACTION"), 2: ("축제", "FESTIVAL"), 3: ("맛집", "FOOD"), 4: ("숙소", "STAY"), 5: ("교통", "TRANSPORT"), 6: ("쇼핑", "SHOPPING"), 7: ("사진", "PHOTO"), 8: ("질문", "QUESTION"), 9: ("후기", "REVIEW")}
_tag_write_lock = asyncio.Lock()


class TagAlreadyExistsError(Exception):
    pass


async def get_tags(db: AsyncSession) -> list[TagResponse]:
    stored = {tag.tag_id: tag for tag in (await db.scalars(select(Tag).order_by(Tag.tag_id))).all()}
    responses = [TagResponse(tag_id=tag_id, name=name, category=category) for tag_id, (name, category) in DEFAULT_TAGS.items()]
    for tag_id, tag in stored.items():
        if tag_id in DEFAULT_TAGS:
            continue
        responses.append(TagResponse(tag_id=tag_id, name=tag.name, category="CUSTOM"))
    return responses


async def create_tag(db: AsyncSession, payload: TagCreate) -> TagResponse:
    async with _tag_write_lock:
        default_names = {name.casefold() for name, _category in DEFAULT_TAGS.values()}
        if payload.name.casefold() in default_names:
            raise TagAlreadyExistsError

        duplicate = await db.scalar(select(Tag.tag_id).where(func.lower(Tag.name) == payload.name.lower()))
        if duplicate is not None:
            raise TagAlreadyExistsError

        max_tag_id = await db.scalar(select(func.max(Tag.tag_id))) or 9
        tag = Tag(tag_id=max(max_tag_id, 9) + 1, name=payload.name)
        db.add(tag)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise
        return TagResponse(tag_id=tag.tag_id, name=tag.name, category="CUSTOM")
