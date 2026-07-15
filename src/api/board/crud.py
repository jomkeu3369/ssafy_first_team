from datetime import datetime
from sqlalchemy import select, func

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.board import Board

async def create_board(db: AsyncSession, note_create: note_schema.NoteCreate, user: Board):
    db_note = Notes(title=note_create.title,
                           content=note_create.content,
                           user_id=user.user_id)
    db.add(db_note)
    await db.commit()
    await db.refresh(db_note)
    return db_note