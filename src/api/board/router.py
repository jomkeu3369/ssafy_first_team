from fastapi import APIRouter, Request

router = APIRouter(prefix="/boards")

@router.get("")
async def get_all_boards(request: Request) -> list[dict]:
    return [{
        "boardId": 1,
        "name": "해운대 게시판",
        "category": "HAEUNDAE",
        "description": "해운대 관광 정보를 공유하는 게시판입니다.",
        "image": "",
        "recentPostCount": 34,
        "lastActivityAt": "2026-07-14T15:30:00+09:00",
        "recentExcerpt": "해운대 야경을 보기 좋은 장소를 공유합니다."
    }]