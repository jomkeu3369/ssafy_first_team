import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data_import import service
from src.api.data_import.schema import BoardTranslationResponse, ErrorResponse, FaissIndexResponse, FaissIndexStatusResponse, ImportResponse, SearchDocumentExportResponse
from src.api.data_import.translation import BoardTranslationFailedError, BoardTranslationUnavailableError, BoardTranslator, get_board_translator
from src.api.comment.translation import CommentTranslationFailedError, CommentTranslationUnavailableError, CommentTranslator, get_comment_translator
from src.api.data_import.schema import CommentTranslationResponse
from src.core.config import get_settings
from src.core.database import get_db_session
from src.mcp_servers.faiss_store import VectorStoreError, load_database_search_documents


router = APIRouter(prefix="/admin/data-import")
settings = get_settings()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


def _authorized(import_key: str | None) -> bool:
    expected = settings.data_import_api_key
    return bool(expected and import_key and hmac.compare_digest(expected, import_key))


def _sync_authorized(sync_key: str | None) -> bool:
    expected = settings.vector_source_api_key
    return bool(expected and sync_key and hmac.compare_digest(expected, sync_key))


@router.get("/search-documents", response_model=SearchDocumentExportResponse, responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def export_search_documents(sync_key: Annotated[str | None, Header(alias="X-MCP-Sync-Key")] = None) -> SearchDocumentExportResponse | JSONResponse:
    if not settings.vector_source_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "Vector source synchronization is not configured.")
    if not _sync_authorized(sync_key):
        return _error(status.HTTP_401_UNAUTHORIZED, "Invalid vector synchronization key.")
    documents, fingerprint = await load_database_search_documents()
    return SearchDocumentExportResponse(documents=documents, fingerprint=fingerprint)


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


@router.post("/board-translations", response_model=BoardTranslationResponse, response_model_by_alias=True, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def translate_board_data(db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[BoardTranslator, Depends(get_board_translator)], import_key: Annotated[str | None, Header(alias="X-Import-Key")] = None, limit: Annotated[int, Query(ge=1, le=100)] = 50) -> BoardTranslationResponse | JSONResponse:
    if not settings.data_import_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "데이터 import API 키가 설정되지 않았습니다.")
    if not _authorized(import_key):
        return _error(status.HTTP_401_UNAUTHORIZED, "데이터 import API 키가 올바르지 않습니다.")
    if not settings.openai_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "OPENAI_API_KEY가 설정되지 않았습니다.")
    try:
        return await service.translate_missing_boards(db, translator, limit)
    except BoardTranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "게시판 번역 기능이 설정되지 않았습니다.")
    except BoardTranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "게시판 데이터를 번역하지 못했습니다.")
    except SQLAlchemyError:
        await db.rollback()
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "게시판 번역을 DB에 저장하지 못했습니다.")


@router.post("/comment-translations", response_model=CommentTranslationResponse, response_model_by_alias=True, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def translate_comment_data(db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[CommentTranslator, Depends(get_comment_translator)], import_key: Annotated[str | None, Header(alias="X-Import-Key")] = None, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> CommentTranslationResponse | JSONResponse:
    if not settings.data_import_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "데이터 import API 키가 설정되지 않았습니다.")
    if not _authorized(import_key):
        return _error(status.HTTP_401_UNAUTHORIZED, "데이터 import API 키가 올바르지 않습니다.")
    if not settings.openai_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "OPENAI_API_KEY가 설정되지 않았습니다.")
    try:
        return await service.translate_missing_comments(db, translator, limit)
    except CommentTranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "댓글 번역 기능이 설정되지 않았습니다.")
    except CommentTranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "댓글을 번역하지 못했습니다.")
    except SQLAlchemyError:
        await db.rollback()
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "댓글 번역을 DB에 저장하지 못했습니다.")


@router.post("/faiss", response_model=FaissIndexResponse, response_model_by_alias=True, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def rebuild_faiss_index(import_key: Annotated[str | None, Header(alias="X-Import-Key")] = None) -> FaissIndexResponse | JSONResponse:
    if not settings.data_import_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "데이터 import API 키가 설정되지 않았습니다.")
    if not _authorized(import_key):
        return _error(status.HTTP_401_UNAUTHORIZED, "데이터 import API 키가 올바르지 않습니다.")
    if settings.vector_mcp_url:
        return _error(status.HTTP_409_CONFLICT, "FAISS is managed by the remote Vector MCP server.")
    if not settings.openai_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "OPENAI_API_KEY가 설정되지 않았습니다.")
    try:
        return await service.rebuild_faiss_index()
    except VectorStoreError:
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "FAISS 인덱스를 생성하지 못했습니다.")


@router.get("/faiss", response_model=FaissIndexStatusResponse, response_model_by_alias=True, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def get_faiss_index_status(import_key: Annotated[str | None, Header(alias="X-Import-Key")] = None) -> FaissIndexStatusResponse | JSONResponse:
    if not settings.data_import_api_key:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "데이터 import API 키가 설정되지 않았습니다.")
    if not _authorized(import_key):
        return _error(status.HTTP_401_UNAUTHORIZED, "데이터 import API 키가 올바르지 않습니다.")
    if settings.vector_mcp_url:
        return _error(status.HTTP_409_CONFLICT, "FAISS status is managed by the remote Vector MCP server.")
    try:
        return await service.get_faiss_index_status()
    except VectorStoreError:
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "FAISS 인덱스 상태를 확인하지 못했습니다.")
