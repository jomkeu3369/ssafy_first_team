import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    @property
    def connected_count(self) -> int:
        return len(self._connections)

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[client_id].add(websocket)
        await self.broadcast_presence()

    async def disconnect(self, client_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(client_id)
            if connections is not None:
                connections.discard(websocket)
                if not connections:
                    self._connections.pop(client_id, None)
        await self.broadcast_presence()

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = [(client_id, websocket) for client_id, connections in self._connections.items() for websocket in connections]
        failed: list[tuple[str, WebSocket]] = []
        for client_id, websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                failed.append((client_id, websocket))
        if failed:
            async with self._lock:
                for client_id, websocket in failed:
                    connections = self._connections.get(client_id)
                    if connections is None:
                        continue
                    connections.discard(websocket)
                    if not connections:
                        self._connections.pop(client_id, None)

    async def broadcast_presence(self) -> None:
        await self.broadcast({"event": "presence.updated", "data": {"connectedCount": self.connected_count}})

    async def broadcast_post_created(self, post_id: int, board_id: int, title: str, created_at: str | None) -> None:
        await self.broadcast({"event": "post.created", "data": {"postId": post_id, "boardId": board_id, "title": title, "createdAt": created_at}})


manager = ConnectionManager()
