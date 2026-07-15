import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data_import import service
from src.api.data_import.schema import ErrorResponse, ImportResponse
from src.core.config import get_settings
from src.core.database import get_db_session


router = APIRouter(prefix="/admin/data-import")
settings = get_settings()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


def _authorized(import_key: str | None) -> bool:
    expected = settings.data_import_api_key
    return bool(expected and import_key and hmac.compare_digest(expected, import_key))


@router.post("/boards", response_model=ImportResponse, response_model_by_alias=True, responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def import_board_data(files: Annotated[list[UploadFile], File(description="부산_*.json 파일들", json_schema_extra={"items": {"type": "string", "format": "binary"}})], db: Annotated[AsyncSession, Depends(get_db_session)], import_key: Annotated[str | None, Header(alias="X-Import-Key")] = None, update_existing: Annotated[bool, Query(alias="updateExisting")] = False) -> ImportResponse | JSONResponse:
    if not settings.data_import_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "데이터 import API 키가 설정되지 않았습니다.")
    if not _authorized(import_key):
        return _error(status.HTTP_401_UNAUTHORIZED, "데이터 import API 키가 올바르지 않습니다.")
    try:
        return await service.import_boards(db, files, update_existing)
    except service.TooManyImportFilesError:
        return _error(status.HTTP_400_BAD_REQUEST, "JSON 파일은 한 번에 1개 이상 10개 이하로 업로드해야 합니다.")
    except service.ImportFileTooLargeError:
        return _error(status.HTTP_413_CONTENT_TOO_LARGE, "JSON 파일 하나의 크기는 5MB 이하여야 합니다.")
    except service.InvalidImportFileError:
        return _error(status.HTTP_400_BAD_REQUEST, "부산 관광 JSON 형식이 올바르지 않습니다.")
    except SQLAlchemyError:
        await db.rollback()
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "데이터를 DB에 저장하지 못했습니다.")
