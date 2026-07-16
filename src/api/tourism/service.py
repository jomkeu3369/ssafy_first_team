import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.api.localization import ATTRACTION_CATEGORY_EN
from src.api.tourism.schema import AttractionCategory, AttractionPageResponse, AttractionResponse, FestivalPageResponse, FestivalResponse, FestivalStatus


class TourismSourceUnavailableError(Exception):
    pass


class TourismContentNotFoundError(Exception):
    pass


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


@lru_cache(maxsize=8)
def _load_items(path_value: str, modified_ns: int) -> tuple[dict[str, Any], ...]:
    del modified_ns
    path = Path(path_value)
    with path.open(encoding="utf-8-sig") as file:
        payload = json.load(file)
    items = payload.get("items")
    if not isinstance(items, list):
        raise TourismSourceUnavailableError
    return tuple(item for item in items if isinstance(item, dict))


def _items(data_dir: Path, filename: str) -> tuple[dict[str, Any], ...]:
    path = data_dir / filename
    if not path.is_file():
        raise TourismSourceUnavailableError
    return _load_items(str(path.resolve()), path.stat().st_mtime_ns)


def _attraction_category(item: dict[str, Any]) -> AttractionCategory:
    target = f"{_text(item.get('title'))} {_text(item.get('addr1'))}"
    if any(keyword in target for keyword in ("해수욕장", "해변", "비치")):
        return AttractionCategory.BEACH
    if any(keyword in target for keyword in ("서면", "남포", "광복", "도심", "시장")):
        return AttractionCategory.DOWNTOWN
    if any(keyword in target for keyword in ("사찰", "성당", "역사", "기념", "문화재", "유적")):
        return AttractionCategory.HISTORIC
    if any(keyword in target for keyword in ("공원", "산", "전망", "섬", "수목원", "생태")):
        return AttractionCategory.SCENIC
    return AttractionCategory.SUBURB


def _to_attraction(item: dict[str, Any]) -> AttractionResponse:
    name = _text(item.get("title"))
    name_en = _text(item.get("titleEn") or item.get("title_en") or item.get("engtitle"))
    address = " ".join(value for value in (_text(item.get("addr1")), _text(item.get("addr2"))) if value)
    address_en = _text(item.get("addr1En") or item.get("addr1_en"))
    overview = _text(item.get("overview"))
    summary = overview[:200] if overview else f"{address}에 위치한 {name}입니다." if address else f"부산의 {name}입니다."
    details = [overview, f"주소: {address}" if address else "", f"전화: {_text(item.get('tel'))}" if _text(item.get("tel")) else ""]
    category = _attraction_category(item)
    summary_en = f"{name_en} is a Busan attraction" + (f" located at {address_en}." if address_en else ".") if name_en else ""
    return AttractionResponse(content_id=_text(item.get("contentid")), name=name, name_en=name_en, category=category, category_en=ATTRACTION_CATEGORY_EN[category.value], summary=summary, summary_en=summary_en, description="\n".join(value for value in details if value) or summary, description_en=summary_en, image=_text(item.get("firstimage")), address=address, address_en=address_en)


def get_attractions(data_dir: Path) -> list[AttractionResponse]:
    return [_to_attraction(item) for item in _items(data_dir, "부산_관광지.json") if _text(item.get("contentid")) and _text(item.get("title"))]


def get_attraction_page(data_dir: Path, page: int, size: int) -> AttractionPageResponse:
    attractions = get_attractions(data_dir)
    offset = (page - 1) * size
    return AttractionPageResponse(items=attractions[offset:offset + size], total=len(attractions), page=page, size=size)


def get_attraction(data_dir: Path, content_id: str) -> AttractionResponse:
    result = next((item for item in get_attractions(data_dir) if item.content_id == content_id), None)
    if result is None:
        raise TourismContentNotFoundError
    return result


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    try:
        return datetime.strptime(text, "%Y%m%d").date() if text else None
    except ValueError:
        return None


def _festival_status(start_date: date | None, end_date: date | None, today: date) -> FestivalStatus:
    if start_date is not None and today < start_date:
        return FestivalStatus.UPCOMING
    if end_date is not None and today > end_date:
        return FestivalStatus.ENDED
    return FestivalStatus.ONGOING


def _to_festival(item: dict[str, Any], today: date) -> FestivalResponse:
    start_date = _parse_date(item.get("eventstartdate"))
    end_date = _parse_date(item.get("eventenddate"))
    start_text = start_date.isoformat() if start_date is not None else _text(item.get("eventstartdate"))
    end_text = end_date.isoformat() if end_date is not None else _text(item.get("eventenddate"))
    period = " ~ ".join(value for value in (start_text, end_text) if value)
    place = _text(item.get("eventplace")) or _text(item.get("addr1"))
    place_en = _text(item.get("eventplaceEn") or item.get("eventplace_en"))
    program = _text(item.get("program"))
    name = _text(item.get("title"))
    name_en = _text(item.get("titleEn") or item.get("title_en") or item.get("engtitle"))
    summary = program[:200] if program else f"{place}에서 열리는 {name}입니다." if place else f"부산에서 열리는 {name}입니다."
    summary_en = f"{name_en} is a festival held" + (f" at {place_en} in Busan." if place_en else " in Busan.") if name_en else ""
    return FestivalResponse(content_id=_text(item.get("contentid")), name=name, name_en=name_en, status=_festival_status(start_date, end_date, today), place=place, place_en=place_en, period=period, period_en=period, start_date=start_date, end_date=end_date, image=_text(item.get("firstimage")), summary=summary, summary_en=summary_en)


def get_festivals(data_dir: Path, today: date | None = None) -> list[FestivalResponse]:
    reference_date = today or date.today()
    return [_to_festival(item, reference_date) for item in _items(data_dir, "부산_축제공연행사.json") if _text(item.get("contentid")) and _text(item.get("title"))]


def get_festival_page(data_dir: Path, page: int, size: int, today: date | None = None) -> FestivalPageResponse:
    festivals = get_festivals(data_dir, today)
    offset = (page - 1) * size
    return FestivalPageResponse(items=festivals[offset:offset + size], total=len(festivals), page=page, size=size)


def get_festival(data_dir: Path, content_id: str, today: date | None = None) -> FestivalResponse:
    result = next((item for item in get_festivals(data_dir, today) if item.content_id == content_id), None)
    if result is None:
        raise TourismContentNotFoundError
    return result
