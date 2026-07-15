from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.api.realtime.manager import manager


router = APIRouter()


@router.websocket("/ws")
async def realtime(websocket: WebSocket, client_id: Annotated[UUID | None, Query(alias="clientId")] = None) -> None:
    resolved_client_id = str(client_id or uuid4())
    await manager.connect(resolved_client_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(resolved_client_id, websocket)
