from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.post.schema import TAG_CATEGORIES
from src.api.tag.schema import TagResponse
from src.models.tag import Tag


DEFAULT_TAGS = {1: ("관광지", "ATTRACTION"), 2: ("축제", "FESTIVAL"), 3: ("맛집", "FOOD"), 4: ("숙소", "STAY"), 5: ("교통", "TRANSPORT"), 6: ("쇼핑", "SHOPPING"), 7: ("사진", "PHOTO"), 8: ("질문", "QUESTION"), 9: ("후기", "REVIEW")}


async def get_tags(db: AsyncSession) -> list[TagResponse]:
    stored = {tag.tag_id: tag for tag in (await db.scalars(select(Tag).order_by(Tag.tag_id))).all()}
    responses = [TagResponse(tag_id=tag_id, name=name, category=category) for tag_id, (name, category) in DEFAULT_TAGS.items()]
    for tag_id, tag in stored.items():
        if tag_id in DEFAULT_TAGS:
            continue
        responses.append(TagResponse(tag_id=tag_id, name=tag.name, category=TAG_CATEGORIES.get(tag_id, "CUSTOM")))
    return responses
