BOARD_CATEGORY_EN = {"FREE": "Free Board", "HAEUNDAE": "Haeundae", "GWANGALLI": "Gwangalli", "SEOMYEON": "Seomyeon", "NAMPODONG": "Nampo-dong", "YEONGDO": "Yeongdo", "GIJANG": "Gijang", "관광지": "Attractions", "레포츠": "Leisure Sports", "문화시설": "Cultural Facilities", "쇼핑": "Shopping", "숙박": "Accommodations", "여행코스": "Travel Courses", "축제공연행사": "Festivals and Events"}
TAG_NAME_EN = {1: "Attraction", 2: "Festival", 3: "Food", 4: "Stay", 5: "Transportation", 6: "Shopping", 7: "Photo", 8: "Question", 9: "Review"}
ATTRACTION_CATEGORY_EN = {"BEACH": "Beach", "DOWNTOWN": "Downtown", "HISTORIC": "Historic Site", "SCENIC": "Scenic Spot", "SUBURB": "Suburban Attraction"}


def board_name_en(name: str, category: str) -> str:
    if name == "전체 자유게시판":
        return "General Community"
    return name or BOARD_CATEGORY_EN.get(category, category)


def board_description_en(description: str | None) -> str | None:
    if description is None:
        return None
    replacements = {"주소:": "Address:", "전화:": "Phone:", "우편번호:": "Postal code:", "행사기간:": "Event period:", "행사장소:": "Venue:", "이용시간:": "Hours:"}
    translated = description
    for korean, english in replacements.items():
        translated = translated.replace(korean, english)
    return translated


def tag_name_en(tag_id: int, name: str) -> str:
    return TAG_NAME_EN.get(tag_id, name)
