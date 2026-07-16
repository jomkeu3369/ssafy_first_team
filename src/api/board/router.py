from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.board import crud
from src.api.board.schema import BoardCreate, BoardPageResponse, BoardResponse, ErrorResponse
from src.api.data_import.translation import BoardTranslationFailedError, BoardTranslationUnavailableError, BoardTranslator, get_board_translator
from src.core.database import get_db_session
from src.models.board import Board


router = APIRouter(prefix="/boards")


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@router.get("", response_model=BoardPageResponse, response_model_by_alias=True)
async def get_boards(db: Annotated[AsyncSession, Depends(get_db_session)], page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 20) -> BoardPageResponse:
    return await crud.get_boards(db, page, size)


@router.get("/{board_id}", response_model=BoardResponse, response_model_by_alias=True, responses={404: {"model": ErrorResponse}})
async def get_board(board_id: Annotated[int, Path(ge=0)], db: Annotated[AsyncSession, Depends(get_db_session)]) -> BoardResponse | JSONResponse:
    board = await crud.get_board(db, board_id)
    return board if board is not None else _error(status.HTTP_404_NOT_FOUND, "게시판을 찾을 수 없습니다.")


@router.post("", response_model=BoardResponse, response_model_by_alias=True, status_code=status.HTTP_201_CREATED, responses={409: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def create_board(payload: BoardCreate, db: Annotated[AsyncSession, Depends(get_db_session)], translator: Annotated[BoardTranslator, Depends(get_board_translator)]) -> Board | JSONResponse:
    try:
        return await crud.create_board(db, payload, translator)
    except crud.BoardAlreadyExistsError:
        return _error(status.HTTP_409_CONFLICT, "같은 이름과 카테고리의 게시판이 이미 존재합니다.")
    except IntegrityError:
        return _error(status.HTTP_409_CONFLICT, "게시판을 생성하지 못했습니다.")
    except BoardTranslationUnavailableError:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "게시판 번역 기능이 설정되지 않았습니다.")
    except BoardTranslationFailedError:
        return _error(status.HTTP_502_BAD_GATEWAY, "게시판을 번역하지 못했습니다.")
