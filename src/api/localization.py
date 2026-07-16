BOARD_CATEGORY_EN = {"FREE": "Free Board", "HAEUNDAE": "Haeundae", "GWANGALLI": "Gwangalli", "SEOMYEON": "Seomyeon", "NAMPODONG": "Nampo-dong", "YEONGDO": "Yeongdo", "GIJANG": "Gijang", "관광지": "Attractions", "레포츠": "Leisure Sports", "문화시설": "Cultural Facilities", "쇼핑": "Shopping", "숙박": "Accommodations", "여행코스": "Travel Courses", "축제공연행사": "Festivals and Events"}
BOARD_CATEGORY_KR = {"FREE": "자유게시판", "HAEUNDAE": "해운대", "GWANGALLI": "광안리", "SEOMYEON": "서면", "NAMPODONG": "남포동", "YEONGDO": "영도", "GIJANG": "기장", "관광지": "관광지", "레포츠": "레포츠", "문화시설": "문화시설", "쇼핑": "쇼핑", "숙박": "숙박", "여행코스": "여행코스", "축제공연행사": "축제공연행사"}
TAG_NAME_EN = {1: "Attraction", 2: "Festival", 3: "Food", 4: "Stay", 5: "Transportation", 6: "Shopping", 7: "Photo", 8: "Question", 9: "Review"}
ATTRACTION_CATEGORY_EN = {"BEACH": "Beach", "DOWNTOWN": "Downtown", "HISTORIC": "Historic Site", "SCENIC": "Scenic Spot", "SUBURB": "Suburban Attraction"}


def board_name_en(name: str, category: str) -> str:
    if name == "전체 자유게시판":
        return "General Community"
    return name if name and not any("가" <= character <= "힣" for character in name) else ""


def board_description_en(description: str | None) -> str | None:
    if description is None:
        return None
    return description if not any("가" <= character <= "힣" for character in description) else None


def contains_hangul(value: str | None) -> bool:
    return bool(value and any("가" <= character <= "힣" for character in value))


def tag_name_en(tag_id: int, name: str) -> str:
    return TAG_NAME_EN.get(tag_id, name)
