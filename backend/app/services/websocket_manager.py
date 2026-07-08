import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class SessionWebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, key: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[key].add(websocket)

    async def disconnect(self, key: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(key)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(key, None)

    async def broadcast(self, key: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._connections.get(key, set()))
            sockets += list(self._connections.get("*", set()))

        stale: list[tuple[str, WebSocket]] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append((key, socket))

        for stale_key, socket in stale:
            await self.disconnect(stale_key, socket)


session_ws_manager = SessionWebSocketManager()
