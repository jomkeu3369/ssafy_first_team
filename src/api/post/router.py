from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.post import crud
from src.api.post.rate_limit import VerifyRateLimiter
from src.api.post.schema import ErrorResponse, PasswordRequest, PasswordVerifyResponse, PostPageResponse, PostResponse, PostSort, PostWrite
from src.api.post.translation import PostTranslator, TranslationFailedError, TranslationUnavailableError, get_post_translator
from src.api.realtime.manager import manager as realtime_manager
from src.core.database import get_db_session


router = APIRouter()
verify_limiter = VerifyRateLimiter()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@router.get("/boards/{board_id}/posts", response_model=PostPageResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_posts(board_id: Annotated[int, Path(ge=0)], db: Annotated[AsyncSession, Depends(get_db_session)], keyword: Annotated[str | None, Query(min_length=1, max_length=200)] = None, sort: PostSort = PostSort.LATEST, page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 10) -> PostPageResponse | JSONResponse:
    try:
        return await crud.get_posts(db, board_id, keyword, sort, page, size)
    except crud.BoardNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시판을 찾을 수 없습니다.")


@router.get("/posts/popular", response_model=PostPageResponse, response_model_by_alias=True)
async def get_popular_posts(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 10) -> PostPageResponse:
    return await crud.get_popular_posts(db, page, size)


@router.get("/posts/{post_id}", response_model=PostResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_post(post_id: Annotated[int, Path(ge=0)], client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)]) -> PostResponse | JSONResponse:
    try:
        return await crud.get_post_with_view(db, post_id, str(client_id))
    except crud.PostNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시글을 찾을 수 없습니다.")


@router.post("/boards/{board_id}/posts", response_model=PostResponse, response_model_by_alias=True, status_code=status.HTTP_201_CREATED, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def create_post(board_id: Annotated[int, Path(ge=0)], payload: PostWrite, client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[PostTranslator, Depends(get_post_translator)]) -> PostResponse | JSONResponse:
    try:
        created = await crud.create_post(db, board_id, payload, str(client_id), translator)
        if created.created_at is not None:
            await realtime_manager.broadcast_post_created(created.post_id, created.board_id, created.title, created.created_at.isoformat())
        return created
    except crud.BoardNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시판을 찾을 수 없습니다.")
    except crud.TagValidationError:
        return _error(status.HTTP_400_BAD_REQUEST, "태그 정보가 올바르지 않습니다.")
    except crud.MediaConflictError:
        return _error(status.HTTP_400_BAD_REQUEST, "이미 사용 중인 미디어입니다.")
    except IntegrityError:
        return _error(status.HTTP_400_BAD_REQUEST, "게시글을 생성하지 못했습니다.")
    except TranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "게시글 번역 기능이 설정되지 않았습니다.")
    except TranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "게시글을 번역하지 못했습니다.")


@router.put("/posts/{post_id}", response_model=PostResponse, response_model_by_alias=True, responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def update_post(post_id: Annotated[int, Path(ge=0)], payload: PostWrite, db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[PostTranslator, Depends(get_post_translator)]) -> PostResponse | JSONResponse:
    try:
        return await crud.update_post(db, post_id, payload, translator)
    except crud.PostNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시글을 찾을 수 없습니다.")
    except crud.PasswordMismatchError:
        return _error(status.HTTP_401_UNAUTHORIZED, "비밀번호가 일치하지 않습니다.")
    except crud.TagValidationError:
        return _error(status.HTTP_400_BAD_REQUEST, "태그 정보가 올바르지 않습니다.")
    except crud.MediaConflictError:
        return _error(status.HTTP_400_BAD_REQUEST, "이미 사용 중인 미디어입니다.")
    except IntegrityError:
        return _error(status.HTTP_400_BAD_REQUEST, "게시글을 수정하지 못했습니다.")
    except TranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "게시글 번역 기능이 설정되지 않았습니다.")
    except TranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "게시글을 번역하지 못했습니다.")


@router.delete("/posts/{post_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def delete_post(post_id: Annotated[int, Path(ge=0)], payload: Annotated[PasswordRequest, Body()], db: Annotated[AsyncSession, Depends(get_db_session)]) -> Response | JSONResponse:
    try:
        await crud.delete_post(db, post_id, payload.password)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except crud.PostNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시글을 찾을 수 없습니다.")
    except crud.PasswordMismatchError:
        return _error(status.HTTP_401_UNAUTHORIZED, "비밀번호가 일치하지 않습니다.")


@router.post("/posts/{post_id}/password/verify", response_model=PasswordVerifyResponse, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
async def verify_post_password(post_id: Annotated[int, Path(ge=0)], payload: PasswordRequest, request: Request, client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)]) -> PasswordVerifyResponse | JSONResponse:
    client_host = request.client.host if request.client is not None else "unknown"
    if not verify_limiter.allow(f"{client_id}:{client_host}:{post_id}"):
        return _error(status.HTTP_429_TOO_MANY_REQUESTS, "비밀번호 확인 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    try:
        await crud.verify_post_password(db, post_id, payload.password)
        return PasswordVerifyResponse(verified=True)
    except crud.PostNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시글을 찾을 수 없습니다.")
    except crud.PasswordMismatchError:
        return _error(status.HTTP_401_UNAUTHORIZED, "비밀번호가 일치하지 않습니다.")
