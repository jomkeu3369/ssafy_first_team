from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.media.schema import ErrorResponse, MediaUploadResponse
from src.api.media.service import FileTooLargeError, InvalidImageError, UnsupportedMediaTypeError, save_image
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.ids import MAX_PUBLIC_ID
from src.models.media import Media


router = APIRouter(prefix="/media")
settings = get_settings()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@router.post("", response_model=MediaUploadResponse, response_model_by_alias=True, status_code=status.HTTP_201_CREATED, responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}})
async def upload_media(request: Request, file: Annotated[UploadFile, File()], db: Annotated[AsyncSession, Depends(get_db_session)]) -> MediaUploadResponse | JSONResponse:
    try:
        starting_id = (await db.scalar(select(func.max(Media.media_id)).where(Media.media_id > 0, Media.media_id <= MAX_PUBLIC_ID)) or 0) + 1
        media_id, filename = await save_image(file, settings.media_dir, starting_id)
    except UnsupportedMediaTypeError:
        return _error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JPEG, PNG, GIF, WebP 이미지만 업로드할 수 있습니다.")
    except FileTooLargeError:
        return _error(status.HTTP_413_CONTENT_TOO_LARGE, "이미지 크기는 2MB 이하여야 합니다.")
    except InvalidImageError:
        return _error(status.HTTP_400_BAD_REQUEST, "올바른 이미지 파일이 아닙니다.")
    image_url = f"{str(request.base_url).rstrip('/')}/media/{filename}"
    return MediaUploadResponse(media_id=media_id, image_url=image_url)
