from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.comment import crud
from src.api.comment.schema import CommentCreate, CommentDelete, CommentPageResponse, CommentResponse, CommentUpdate, ErrorResponse
from src.api.comment.translation import CommentTranslationFailedError, CommentTranslationUnavailableError, CommentTranslator, get_comment_translator
from src.core.database import get_db_session


router = APIRouter()


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@router.get("/posts/{post_id}/comments", response_model=CommentPageResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_comments(post_id: Annotated[int, Path(ge=1)], db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> CommentPageResponse | JSONResponse:
    try:
        return await crud.get_comments(db, post_id, page, size)
    except crud.PostNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시글을 찾을 수 없습니다.")


@router.post("/posts/{post_id}/comments", response_model=CommentResponse, response_model_by_alias=True, status_code=status.HTTP_201_CREATED, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def create_comment(post_id: Annotated[int, Path(ge=1)], payload: CommentCreate, client_id: Annotated[UUID, Header(alias="X-Client-Id")], db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[CommentTranslator, Depends(get_comment_translator)]) -> CommentResponse | JSONResponse:
    try:
        return await crud.create_comment(db, post_id, payload, str(client_id), translator)
    except crud.PostNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "게시글을 찾을 수 없습니다.")
    except crud.ParentCommentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "부모 댓글을 찾을 수 없습니다.")
    except crud.CommentDepthError:
        return _error(status.HTTP_400_BAD_REQUEST, "대댓글에는 답글을 작성할 수 없습니다.")
    except IntegrityError:
        await db.rollback()
        return _error(status.HTTP_400_BAD_REQUEST, "댓글을 생성하지 못했습니다.")
    except CommentTranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "댓글 번역 기능이 설정되지 않았습니다.")
    except CommentTranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "댓글을 번역하지 못했습니다.")


@router.put("/comments/{comment_id}", response_model=CommentResponse, response_model_by_alias=True, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def update_comment(comment_id: Annotated[int, Path(ge=1)], payload: CommentUpdate, db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[CommentTranslator, Depends(get_comment_translator)]) -> CommentResponse | JSONResponse:
    try:
        return await crud.update_comment(db, comment_id, payload.content, payload.password, translator)
    except crud.CommentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "댓글을 찾을 수 없습니다.")
    except crud.PasswordMismatchError:
        return _error(status.HTTP_401_UNAUTHORIZED, "비밀번호가 일치하지 않습니다.")
    except CommentTranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "댓글 번역 기능이 설정되지 않았습니다.")
    except CommentTranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "댓글을 번역하지 못했습니다.")


@router.delete("/comments/{comment_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT, responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def delete_comment(comment_id: Annotated[int, Path(ge=1)], payload: Annotated[CommentDelete, Body()], db: Annotated[AsyncSession, Depends(get_db_session)]) -> Response | JSONResponse:
    try:
        await crud.delete_comment(db, comment_id, payload.password)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except crud.CommentNotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "댓글을 찾을 수 없습니다.")
    except crud.PasswordMismatchError:
        return _error(status.HTTP_401_UNAUTHORIZED, "비밀번호가 일치하지 않습니다.")
