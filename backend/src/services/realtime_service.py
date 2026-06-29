from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger("dart.realtime")


class RealtimeNotificationManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, username: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[username].add(websocket)

    async def disconnect(self, username: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(username)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(username, None)

    async def send_notification(self, notification: dict[str, Any]) -> int:
        username = str(notification.get("user") or "")
        async with self._lock:
            connections = list(self._connections.get(username, set()))
        delivered = 0
        stale: list[WebSocket] = []
        payload = {"type": "notification", "notification": notification}
        for websocket in connections:
            try:
                await websocket.send_json(payload)
                delivered += 1
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(username, websocket)
        logger.info(
            "REALTIME_NOTIFICATION_SENT notification_id=%s user=%s connections=%s",
            notification.get("id", ""),
            username,
            delivered,
        )
        return delivered


realtime_manager = RealtimeNotificationManager()


def publish_from_sync(notification: dict[str, Any]) -> None:
    """Publica desde endpoints sync ejecutados por el threadpool de FastAPI."""
    try:
        from anyio import from_thread

        from_thread.run(realtime_manager.send_notification, notification)
    except RuntimeError:
        # Las llamadas unitarias directas no viven en un worker AnyIO.
        return
